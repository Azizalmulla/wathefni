# Auth Wave 2 Phase 3B — navigation preserve under unlock overlay

**Stamp:** `20260807T035603Z`  
**Verdict:** Phase 3B **under review** — nav preserve fix shipped; physical confirm required  
**Phase 4:** not started

## Code-path audit (live)

| Path | Navigation / remount? |
|---|---|
| Under timeout resume | No — `needsLocalUnlock` stays false; AuthGate/Stack untouched |
| Over timeout | Sets `needsLocalUnlock` only — **children stay mounted** |
| Face ID success | `onUnlocked()` → `setNeedsLocalUnlock(false)` only — **no** `setStatus`, **no** `router.*` |
| Cancel → PIN → unlock | Same dismiss path |
| AuthGate | `router.replace('/(tabs)')` only when `signedIn && inAuthGroup` — overlay never leaves `signedIn` or auth group |
| PushLifecycle | Disabled (`PUSH_REGISTRATION_ENABLED=0`) — no `/notifications` push |
| ForegroundQueryRefresh | Soft refetch only; now **skipped while overlay up** |

**By design the nav tree was already preserved.** The suspected physical “wrong screen” was RN **`Modal` vs native-stack**: presenting/dismissing Modal (esp. around Face ID) can restore the wrong UIViewController even though React route state is intact.

## Fix

- **iOS:** unlock host = `FullWindowOverlay` (above native stack, no Modal)
- **Android:** keep `Modal` (z-order)
- Skip privacy cover while overlay is up (Face ID → `inactive`)
- Skip foreground query refetch while overlay is up

Timeout + Face ID gate logic unchanged.

## OTA

| Field | Value |
|---|---|
| Group | `9a9a11be-dc9a-4e01-a1ec-f6f98bc5e2de` |
| Prior | `9aa012bf-dec5-4c54-9bf0-db525484eeca` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/9a9a11be-dc9a-4e01-a1ec-f6f98bc5e2de |

## Unit

60/60 PASS

## Physical confirm (required before Phase 3B fully proven)

1. Open **Settings** (or Bank / Onboarding — a non-Home screen)
2. Background ≥40s → Face ID unlock
3. Must return to the **same screen** (and scroll if noticeable)
4. Repeat with Face ID cancel → PIN unlock — same screen
5. Under-timeout resume — same screen, no overlay

Do not start Phase 4.
