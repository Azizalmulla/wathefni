# Auth Wave 2 Phase 3 — false-positive lock fix

## Verdict

**not proven** — prior OTA locked on every leave/return. Fix republished for re-qual. Do **not** start Phase 4.

## Root cause

1. Away clock + timer + device probe armed on `inactive` (Control Center, notification shade, Face ID system UI, app-switcher peek).
2. iOS `isProtectedDataAvailable` false positives during inactive → treated as device lock → **immediate seal** even after a few seconds.
3. Resume logged a combined reason; timers were not clearly cancelled before decision.

## Fix

- Arm **only** on AppState `background` (inactive ignored for lock arming).
- Device probe only after settled in `background` (600ms); skip if no longer background.
- Resume cancels timeout + probe timers first, then decides:
  - `timeout` — entered background and elapsed ≥ saved timeout
  - `confirmed_device_lock` — probe true while backgrounded
  - `none` — inactive-only return, or short background
- Duplicate seal prevented per away cycle.
- Timer delay uses `autoLockTimeoutRef` (saved timeout).

## OTA

- Group: `0ac5d3b9-442e-422d-8bcc-39d0b1027346`
- Dashboard: https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/0ac5d3b9-442e-422d-8bcc-39d0b1027346
- Rollback: `6cffdfd1-a7d9-4b1e-9d9e-5bb731fc2e5f`

## Device retest

1. Force-quit → reopen (load this OTA); Auto-lock = 30 seconds
2. Background / switch app 5–15s → **no** Face ID/PIN (`reason: none`)
3. Background ≥40s → Face ID/PIN (`reason: timeout`)
4. Lock phone while app backgrounded → Face ID/PIN (`reason: confirmed_device_lock`)
5. Control Center / notification shade briefly → **no** lock
