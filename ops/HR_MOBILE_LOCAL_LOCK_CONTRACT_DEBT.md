# HR mobile Local Lock — contract debt

**Status:** Auth Wave 2 Phases 0–5 parity shipped for HR (2026-08-10).  
**Boundary:** Local security shell only — operator `/dashboard/mobile/auth/*` sessions stay separate from Employee.

## Locked product shape

| Surface | Behavior |
| --- | --- |
| PIN / Face ID / auto-lock | Same UX primitives as Employee; HR-namespaced SecureStore (`wathefni.hr.pin.*`, `wathefni.hr.biometric.*`, `wathefni.hr.autolock.*`) |
| Principal binding | `company_code:user_id` — never `employee_key` |
| Recovery | Operator email/password re-auth after Forgot PIN / 5 fails — not OTP activation |
| Mount | `HRLocalUnlockShell` wraps HR `AccessGate` when `shell.kind === 'hr'` |
| Mode switch | Employee and HR keep independent lock material; switching remounts the other shell |
| Settings | Device security section: bio toggle, auto-lock timeouts, Change PIN |
| Masters | Shared `EXPO_PUBLIC_LOCAL_*` flags with Employee |

## Known gaps / remaining parity debt

| Gap | Current | Desired long-term |
| --- | --- | --- |
| Device security card (`GET /app/device-security`) | Omitted on HR (employee endpoint) | Optional operator device card if product wants parity copy without employee API |
| Auto-lock diagnostics panel | Not on HR Settings | Only if `EXPO_PUBLIC_LOCAL_AUTO_LOCK_DIAGNOSTICS=1` and product asks |
| Locale RTL restart skip-unlock-once | Employee has dual markers; HR not wired | Add `wathefni.hr.pin.skip_unlock_once` if HR locale restart needs same skip |
| Push on HR | Still none | Separate operator push model |
| Phase 6 device screen-lock | Not started (matches Employee) | Stay deferred |
| Physical Face ID QA on HR | Canary OTA; physical pending | Owner device pass |

## Explicitly out of scope

Session merge · `/app/auth/*` for operators · Employee SecureStore reuse · Phase 6 · inventing HR push.
