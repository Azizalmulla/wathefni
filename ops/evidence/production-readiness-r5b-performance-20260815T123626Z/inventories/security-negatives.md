# R5B security negatives

Direct HTTP via FastAPI TestClient with `dashboard_context` / `employee_app_context` overrides. `permission_authority=backend_current` required. Second tenant `COMPANY_B` for isolation.

| Case | Result |
|---|---|
| Unauthenticated dashboard | 401/403 — not public, not SPA 404 |
| Unauthenticated employee | 401/403/503 — not public (503 = employee app platform disabled, still fail-closed) |
| Tenant isolation | Other-company objective 404 |
| Employee enumerate others | Other employee goals empty / IDOR 404 |
| Employee update others' progress | 403 `progress_not_owned` |
| Manager empty scope | Fail-closed empty list, not company-wide |
| Manager calibration | 403 |
| Manager launch cycle | 403 `cycle_admin_required` |
| Raw 360 without `performance.sensitive` | 403 |
| Employee 360 identities | Redacted when anonymous |
| Calibration unauthorized | 403 |
| Module disabled writes | Blocked; history kept |
| Talent namespaces | Live 404 `capability_not_released` |
| Client `X-Company-Code` | Not treated as write authority in `performance_http` |
| Public endpoint | None. All routes depend on authenticated context |

R2 staging DB regression: **69 passed, 0 failed** (`R2_SECURITY_FULL_PASS`).
Internal-auth staging: **10 passed, ALL CHECKS PASSED**.
