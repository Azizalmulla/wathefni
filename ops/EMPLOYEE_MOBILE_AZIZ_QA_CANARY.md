# Employee Mobile — Aziz QA Canary (second internal)

**Stamp:** `20260805T031400Z`  
**Purpose:** Let Aziz activate the employee app on his own phone without using Talal’s device.  
**Tenant:** `WATHEFNI` only · Talal canary preserved

## Activation (use in the app)

| Field | Value |
|---|---|
| App phone field (UI already shows +965) | `99338566` |
| Full digits (also accepted) | `96599338566` / `+96599338566` |
| Activation code | `221913` |
| Expires | ~2026-08-06 03:39 UTC |

Enter **only** `99338566` in the phone field (do not re-type 965 — the chip already shows it), then code **`221913`**.

### Edge + activation path fix (2026-08-05)

1. Caddy now proxies `/app*` → orchestrator (was public 404).
2. Activate accepts Kuwait **local 8-digit** phone aliases so the app’s `+965` chip + `99338566` matches invites stored as `96599338566`.

Prior codes (`242778`, `373866`, proof `149359`) are spent — use **`221913`** only.

See `ops/EMPLOYEE_MOBILE_ACTIVATION_PATH_FIX.md`.

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
