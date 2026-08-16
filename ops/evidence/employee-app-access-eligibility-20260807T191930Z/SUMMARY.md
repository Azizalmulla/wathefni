# Employee App Access Eligibility + Invite Trigger

| Field | Value |
|---|---|
| Stamp | `20260807T191930Z` |
| Verdict | **PASS** |
| Company | WATHEFNI (canary) |
| Contract | `employee_app_access_eligibility_v1` |
| Design | `ops/EMPLOYEE_APP_ACCESS_ELIGIBILITY.md` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-app-access-eligibility-20260807T191930Z/ROLLBACK.sh` |
| Dashboard | `PostHire-BpOFfS5m.js` |

## Exact eligibility model

```text
Invite iff:
  WATHEFNI_EMPLOYEE_APP platform on
  AND company_modules.employee_app.enabled
  AND employees.app_access_enabled = true
  AND employment_status active
```

- Company OFF → zero invites (HR/Payroll/E360/Migration still work)
- Create / onboarding start / Migration import → never set flag, never invite
- Enable employee (or bulk keys/departments/all) → existing invite+delivery
- Disable → clear flag + existing revoke/session semantics
- Device Revoke → sessions only; flag unchanged → Re-invite allowed

## Proven

| Check | Result |
|---|---|
| Company OFF + create → no invite | PASS |
| Company ON + employee OFF → no invite | PASS |
| Enable employee → invite delivered | PASS |
| Re-enable idempotent (no spam) | PASS |
| Bulk-import style creates → no invites | PASS |
| Enable selected only | PASS |
| Enable department group (deduped) | PASS |
| Disable blocks invites | PASS |
| Revoke + Re-invite still works | PASS |
| Invitation smoke (post-eligibility) | PASS |
| No Auth Wave 2 Phase 6 | PASS |

## Remaining gaps

- Setup Console deep UX for company access_mode / departments (API ready)
- Owner live walk of Enable access & invite on profile
- Auth Wave 2 Phase 6 — not started
