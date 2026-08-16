# Setup Console Phase 1 — qualification

**Verdict: PASS**

| Check | Result |
|---|---|
| Canonical ownership map | PASS |
| Employee App company policy writes consolidated to Setup | PASS |
| PostHire company policy PATCH refused | PASS (route guard `company_app_access_owned_by_setup_console`) |
| Deep links (`#classic-*` + `/dashboard?page=`) | PASS |
| Live ownership + employee-app-access API | PASS |
| Tenant-scoped policy (`WATHEFNI`) | PASS |
| Module disable semantics contract | PASS (exception: `employee_app` session/invite close) |
| Dist contains ownership UI strings | PASS |
| Canary deploy (dual-tree + dashboard-dist) | PASS |

Smoke: `PASS=21 FAIL=0`  
Doc: `ops/SETUP_CONSOLE_PHASE1_OWNERSHIP.md`  
**Phase 2 not started.**
