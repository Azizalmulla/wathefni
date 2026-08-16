# Employee App — Access Eligibility + Invite Trigger

**Status:** ACTIVE — canary (WATHEFNI)  
**Contract:** `employee_app_access_eligibility_v1`  
**Out of scope:** Auth Wave 2 Phase 6 · SMS · new identity model

## Canonical rule

```text
Employee exists in Employee 360
  AND company Employee App module is ON
  AND employee.app_access_enabled = true
→ Wathefni issues + delivers activation invite
```

Mere employee **create**, **onboarding start**, or **Migration & Sync import** never sends invites and never sets `app_access_enabled`.

## Eligibility model

| Layer | Storage | Meaning |
|---|---|---|
| Platform | `WATHEFNI_EMPLOYEE_APP` | Master dark-launch for `/app/*` |
| Company | `company_modules.employee_app.enabled` | Off → zero invites for the company |
| Company policy | `company_modules.employee_app.settings.access_mode` | `selected` (default) or `all` (bulk-enable UX) |
| Company groups | `settings.selected_departments` | Used by bulk enable / policy sync |
| Employee | `employees.app_access_enabled` (default **false**) | Explicit enable required for invites |

Module: `employee_app_access.py`  
Invite issuance still owned by `employee_app_invitation.py` + hashed codes / 24h / email·WhatsApp ladder.

## Triggers

| Event | Invite? |
|---|---|
| Create employee | **No** |
| Onboarding start | **No** |
| Migration import/sync | **No** (flags stay false) |
| Enable employee access | **Yes** (idempotent auto deliver) |
| Bulk enable keys / departments / all active | **Yes** for those employees only |
| Company policy sync (`all` / departments) | Bulk-enables then invites |
| Disable employee access | Blocks invites + reuses revoke/session semantics |
| Device Revoke (existing) | Sessions killed; eligibility flag unchanged → Re-invite allowed |

## HR APIs

| Route | Role |
|---|---|
| `GET/PATCH .../app-access/policy` | Company on/off + mode + departments |
| `POST .../app-access/eligibility` | Enable/disable one employee (+ invite on enable) |
| `POST .../app-access/enable-bulk` | Selected keys / departments / all active |
| Existing invitation + revoke routes | Unchanged Auth Wave 2 / delivery |
