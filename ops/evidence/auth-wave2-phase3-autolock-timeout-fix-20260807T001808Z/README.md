# 20260806 — Auth Wave 2 Phase 3 timeout-path fix

## Verdict

**not proven** — timeout path failed on physical device (bg ≥40s, no Face ID/PIN). Fix republished; re-qualify. Do **not** mark Phase 3 proven. Do **not** start Phase 4.

## Likely failure modes on fda08e77

1. AppState listener re-subscribed on `me` / `refreshMe` changes (stale/torn listener risk)
2. Lock decision deferred behind async device-lock probe
3. No background timer — relied only on resume, which can miss/race on iOS
4. Insufficient diagnostics to confirm OTA id / timeout / elapsed

## Fix

- Mount-once AppState listener; all live values via refs
- Arm `awayStartedAt` when leaving `active` → `inactive|background`
- Schedule background timer to seal at timeout (in addition to resume check)
- Synchronous resume seal for timeout/device-lock (no await before decision)
- Logs: `[autolock] boot config | away start | schedule | timer fired | resume decision | SEALED` including `updateId`, timestamps, elapsed, timeout, enabled

## OTA

- Group: `6cffdfd1-a7d9-4b1e-9d9e-5bb731fc2e5f`
- Dashboard: https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/6cffdfd1-a7d9-4b1e-9d9e-5bb731fc2e5f
- Env: PIN=1 BIOMETRIC=1 AUTO_LOCK=1
- Rollback prior: `fda08e77-f7a1-464c-8596-00cc4e4c6461`

## Re-test (timeout path only)

1. Force-quit → reopen (load OTA `6cffdfd1-…`; confirm Settings → Auto-lock = **30 seconds**, not Never)
2. Unlock → use app → background ≥40s → return → **must** Face ID/PIN
3. Background &lt;20s → return → stay unlocked
4. Optional: Mac Console / device logs filter `autolock` — expect `away start`, `resume decision` with `elapsedMs≥30000`, `SEALED`

Screen-lock native testing remains separate.
