# HR Employee Profile — cream honesty ship

Stamp: `20260810T180148Z`  
Surface: `/hr/employees/[employeeKey]`  
Mode: **ship + freeze**

## Functional verdict: **PASS — FROZEN**

Facts-only cream quick profile. No E360. No manager_name. Localized employment status. Empty/missing keys never blank ready.

## Ship

| Field | Value |
| --- | --- |
| OTA | `66eab204-7f74-441b-8df2-b54a8ec8cf45` |
| iOS update | `019fecd7-a208-74cf-aced-c3157b14d130` |
| Runtime | 0.3.0 · canary |
| Gates | verify-hr-employee-profile · physical-hr-employee-profile-en-ar · verify-hr-people-directory · tsc · spine-probe |
| Freeze | `.cursor/rules/hr-mobile-employee-profile-freeze.mdc` |
| Debt | `ops/HR_MOBILE_EMPLOYEE_PROFILE_CONTRACT_DEBT.md` |

## Live spine

- Sample profile keys exclude manager_name
- Missing key → 404 employee_not_found
- Status `active` localized on client

Next: remaining confirmation / file / auth qualification matrix (no Employee Profile redesign).
