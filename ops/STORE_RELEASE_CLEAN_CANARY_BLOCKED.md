# Clean Setup canary — BLOCKED

**Date:** 2026-08-16  
**Tenant:** `QACD18D1` (and earlier `QAB45967`) on staging  
**Evidence:** `ops/evidence/store-release-clean-canary-*`

Setup Console on live staging (after restoring `setup_console_operator_auth.py` to the staging tree):

| Step | Result |
|---|---|
| Operator login | PASS |
| Create company | PASS — empty bootstrap |
| PATCH catalog modules (`leave`, `attendance`, `onboarding`, `employee_app`) | PASS |
| Seed owner + accept invite + dashboard login | PASS |
| Owner GET company Setup | PASS |
| Owner PATCH leave module-policies | PASS |
| Owner `POST /dashboard/posthire/employees` | **FAIL 403 `permission_denied`** |

`employees.read` / `employees.manage` are grant-only and stripped from every role, including `owner`. `set_dashboard_user_permission_grant` refuses to grant a permission the actor does not already hold. Setup `team-access` is GET-only. The first grant historically required the reviewed cutover CLI.

This is not a test-harness gap. A real company configured only through Setup cannot staff a roster.

SQL-granting the matrix would fake a pass and violate “no developer intervention.” Stop for owner.
