# Employee Mobile — Aziz QA Canary (second internal)

**Stamp:** `20260805T031400Z`  
**Purpose:** Let Aziz activate the employee app on his own phone without using Talal’s device.  
**Tenant:** `WATHEFNI` only · Talal canary preserved

## Activation (use in the app)

| Field | Value |
|---|---|
| Phone (app field) | `96599338566` |
| Phone (E.164) | `+96599338566` |
| Activation code | `242778` |
| Expires | ~2026-08-06 03:14 UTC (~24h from issue) |

In the Wathefni employee app: enter **`96599338566`** and code **`242778`**.

## Identity

| Field | Value |
|---|---|
| Employee key | `WATHEFNI-96599338566` |
| Name | `W5C-SYNTH\|Aziz Mobile QA` |
| Position | Mobile QA Tester |
| Department | Internal QA |
| Authority | Normal employee ESS only (no payroll money, hiring, HR-admin, manager) |

## Allowlist (narrow)

```
WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST=WATHEFNI-96550252254,WATHEFNI-96599338566
```

Talal `WATHEFNI-96550252254` unchanged. No broad GA.

## Seeded fixtures (this employee only)

- Onboarding Wave2 checklist: **36** items (`in_progress`)
- Shifts: today + upcoming QA shifts
- Leave: 1 approved + 1 requested
- Attendance: recent present/late/absent rows
- Notifications: shift / leave / onboarding / compliance inbox rows  
All tagged `metadata.qa=employee_mobile` / synthetic markers.

## Scoping confirmation

- Company: **WATHEFNI**
- Session/API bound to `WATHEFNI-96599338566` only
- Talal row after provision: still `Talal Fadhli` / `96550252254`
- `/app/*` smoke for Aziz QA: me/onboarding/leave/shifts/attendance/notifications/documents/profile **200**

## Rollback

1. Remove `,WATHEFNI-96599338566` from both systemd drop-ins that set `WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST`, daemon-reload, restart orchestrator.  
2. Optionally delete QA fixtures:  
   `DELETE FROM … WHERE employee_key='WATHEFNI-96599338566' AND metadata->>'qa'='employee_mobile'`  
   and/or soft-offboard the employee if no longer needed.  
**Do not** change Talal’s allowlist entry when rolling back Aziz only.
