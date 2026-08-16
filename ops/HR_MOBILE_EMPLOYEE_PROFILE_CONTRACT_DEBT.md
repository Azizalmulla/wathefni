# HR mobile Employee Profile — contract debt

Locked with cream honesty ship `20260810T180148Z`. Residuals, not freeze blockers.

1. **Restrained module deep-links** (Attendance / Leave / Onboarding / Documents / Shifts) deferred — facts-only v1 locked; do not invent a module dashboard here.
2. **Manager name** omitted until `mobile_employee_quick_profile` returns a resolved name from assignment truth.
3. **Empty position/department** on some roster cards is API truth — hide empty facts; do not invent placeholders.
4. **List cold-start** `/hr/employees` → More (mild IA debt); detail cold-start correctly → People.
5. **Capability vs list `module_disabled`** mismatch when `employees.read` exists but no post-hire module reads — People/list debt, not profile chrome.
6. Web Employees 360 remains under `employees360-freeze` — mobile must not port it.
