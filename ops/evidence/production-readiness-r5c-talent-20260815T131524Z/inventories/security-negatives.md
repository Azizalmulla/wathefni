# R5C security negatives

Direct HTTP via FastAPI TestClient with `dashboard_context` / `employee_app_context` overrides. `permission_authority=backend_current` required. Second tenant `COMPANY_B` for isolation.

| Case | Result |
|---|---|
| Unauthenticated dashboard | 401/403 — not public |
| Unauthenticated employee | 401/403/503 — not public |
| Tenant isolation | Other-company profile 404 |
| Employee internal judgments | `/app/talent` has no `potential` / `hipo` / `succession` |
| Employee IDOR | Other key does not return the original employee's profile |
| Manager empty scope | Fail-closed empty list (`total=0`) |
| Manager HiPo without `talent.sensitive` | 403 |
| Manager succession without `talent.succession` | 403 |
| HR without write permission | POST `/profiles` 403 |
| Module disabled writes | Blocked; history kept |
| JA / Learning namespaces | Live 404 `capability_not_released` |
| Client `X-Company-Code` | Not treated as write authority in `talent_http` |
| Public endpoint | None. All routes depend on authenticated context |

R2 staging DB regression: **69 passed, 0 failed** (`R2_SECURITY_FULL_PASS`).
Internal-auth staging: **10 passed, ALL CHECKS PASSED**.
