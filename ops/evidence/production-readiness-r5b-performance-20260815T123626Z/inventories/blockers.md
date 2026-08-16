# R5B blockers

**Open R5B blockers: none.**

Resolved during qualification:

1. **HTTP routes never registered.** `register_performance_http` ran inside an early `try/except: pass` before `_posthire_read_context` / `employee_app_context` existed. `AttributeError` was swallowed; GET hit the SPA catch-all. Fixed by registering after `employee_app_context` and not swallowing exceptions.
2. **Unauthenticated employee 503.** Staging employee-app platform may return 503 `employee_app_disabled` before auth. Treated as not-public / fail-closed alongside 401/403.
3. **Inventory generation cwd.** Qualify step 7 used a relative path after `cd` into the orchestrator. Fixed to `cd "$REPO_ROOT"`. Inventories in this stamp were written from the same sources the tests ran against.
