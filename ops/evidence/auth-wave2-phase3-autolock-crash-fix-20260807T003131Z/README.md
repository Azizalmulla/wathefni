# Auth Wave 2 Phase 3 — resume crash fix

## Verdict

**failed** (physical crash on resume under `0ac5d3b9-…`). Rolled back, then crash-fix republished. Phase 3 is **not proven**. Do **not** start Phase 4.

## Crash diagnosis (no USB device on agent)

Physical report: Face ID OK → leave → return → **hard crash** (not calm unlock).

Most likely failure mode (code-path analysis; matches iOS symptoms):

1. **State update during AppState transition / from background**  
   `0ac5d3b9` called `setStatus('locked')` from background timer / device-probe callbacks. That remounts `AuthGate` (unmounts navigation Stack, mounts biometric unlock) while iOS is still transitioning → native crash or uncaught render fault.

2. **Biometric re-entry during resume**  
   Unlock gate immediately presented `LocalAuthentication` on mount as AppState became `active` — known iOS crash window for LAContext.

3. Less likely but guarded: duplicate seal/unseal, in-flight probe after resume, `Updates.createdAt.toISOString` if non-Date.

Device Console was empty on the agent Mac (no attached phone). `AppErrorBoundary` now logs `[AppErrorBoundary]` with stack — if the fault is a JS render error, filter that; if the process dies with no JS log, it was native (LA / navigation).

## Immediate rollback

Republished pre-crash group `fda08e77-…` as:
- Rollback live group: `83fe64f6-a46f-4cfb-b6ed-6e7229a6c27a`

## Fix (this stamp)

- Single **resume coordinator** — only one path decides `timeout` | `confirmed_device_lock` | `none`
- Background timer/probe record **intent refs only** — **never** `setStatus` while not `active`
- Cancel all timers before resume decision; block duplicate resume/seal
- Delay Face ID prompt ~450ms until AppState stably `active`; block duplicate prompts
- Safer `Updates.createdAt` logging; ForegroundQueryRefresh catch

## Fix OTA

- Group: `fdb4002c-d014-4cd1-aa12-0ff2f76aaa76`
- Dashboard: https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/fdb4002c-d014-4cd1-aa12-0ff2f76aaa76

## Required re-prove

1. Force-quit → reopen (load `fdb4002c-…`)
2. 10s away → no prompt, **no crash**
3. 40s away → **one** Face ID/PIN, no crash
4. Phone lock → one prompt, no crash
5. Control Center → no prompt, no crash
6. Rapid background/resume ×10 → no crash

If crash persists, republish `83fe64f6-…` again and capture Mac Console / Xcode devices log for `[autolock]` / `[AppErrorBoundary]` / `LocalAuthentication`.
