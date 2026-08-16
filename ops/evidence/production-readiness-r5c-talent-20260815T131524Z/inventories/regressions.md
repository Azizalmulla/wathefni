# R5C regressions

All local unit scripts `rc=0`. Staging DB R2–R5B green.

| Suite | Result |
|---|---|
| Dashboard named vitest | 4 files, 39 passed |
| Dashboard full vitest | **89 files, 481 passed, 0 failed** |
| Employee composition | 65 checks including talent-only Home tile |
| R5C unit | **59 passed, 0 failed** `R5C_TALENT_SURFACE_UNIT_PASS` |
| R5B unit | **55 passed, 0 failed** `R5B_PERFORMANCE_SURFACE_UNIT_PASS` |
| R5A unit | **173 passed, 0 failed** `R5A_CAPABILITY_HONESTY_UNIT_PASS` |
| R5C staging DB | **62 passed, 0 failed** `R5C_TALENT_SURFACE_DB_PASS` |
| R5B staging DB | **62 passed, 0 failed** `R5B_PERFORMANCE_SURFACE_DB_PASS` |
| R5A staging DB | **30 passed, 0 failed** `R5A_CAPABILITY_HONESTY_DB_PASS` (Talent now customer-usable; Wave 6 still refused) |
| Live staging service | **11 passed, 0 failed** |
| Wave 6 product acceptance | rc=0 |
| Job Architecture C1 | rc=0 |
| Learning C2 | rc=0 |
| Benefits C3 | rc=0 |
| Employee Relations C4 | rc=0 |
| Engagement C5 | rc=0 |
| Compensation Planning C6 | rc=0 |
| Workforce Planning C7 | rc=0 |
| Wave 5 product acceptance | rc=0 |
| Wave 4 product acceptance | rc=0 (honesty now records Talent enableable after R5C) |
| Wave 3 product acceptance | rc=0 |
| Wave 2 product acceptance | rc=0 |
| Wave 1 product acceptance | rc=0 |
| Talent profile C5 | rc=0 (unit; empty allowlist admits after R5C) |
| Talent succession C6 | rc=0 (unit; empty allowlist admits after R5C) |
| R2 security unit | rc=0 |
| R3 data-safety unit | rc=0 |
| R4 truth-in-UI unit | rc=0 |
| Interaction authority contracts | OK |
| Internal-auth staging | ALL CHECKS PASSED |
| R2 security staging DB | `R2_SECURITY_FULL_PASS` 69/0 |
| R3 data-safety staging DB | `R3_DATA_SAFETY_FULL_PASS` 18/0 |
| R4 truth-in-UI staging DB | `R4_TRUTH_IN_UI_DB_PASS` 9/0 |

R2, R3, R4, R5A, and R5B remain frozen. R5A live script that expected `/dashboard/posthire/talent` 404 `capability_not_released` is **not** an R5C verdict.
