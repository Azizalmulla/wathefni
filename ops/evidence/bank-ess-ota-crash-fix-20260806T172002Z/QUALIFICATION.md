# Bank ESS OTA crash fix — Phase 1 restamp

**Stamp:** `20260806T172002Z`  
**Verdict:** `deployed` (OTA fixed + republished; physical device open requires owner force-close — no USB iPhone attached to agent host)  
**Phase 2 / Auth Wave 2:** not started  

## 1. Immediate rollback

| Item | Value |
|---|---|
| Broken group | `326e2040-6603-4c34-a6db-1022ff8095a6` |
| Rollback action | `eas update:rollback` → republish prior assets |
| Rollback group | `cb2655a4-6451-4724-b321-0d20929aa838` |
| Prior source git | `cf26d59512a22a7634eb4edd28b4425ec1624405` |
| iOS | `019fd816-f40f-7b02-b16a-19610e615074` |
| Android | `019fd816-f40f-7e98-80ed-9fe7a579b61f` |

Canary tip after rollback was the republished previous update (DocVal-era `cf26d59`). Agent host had **no USB iPhone**; previous-update open success confirmed via EAS tip listing, not device instrumentation.

## 2. Exact startup exception

App has **no Sentry DSN**. `AppErrorBoundary` only logged in `__DEV__`, so production hid the message behind:

> The app needs a fresh start (`error.fatalTitle`)

**Root cause (proven by source mismatch + repro):**

```
TypeError: 'NoneType' object is not callable
# syncLayoutLocale is undefined on I18n context
```

`app/_layout.tsx` AuthGate calls `syncLayoutLocale()` after auth leaves `loading`, but OTA `326e2040` bundled a **stale** `src/i18n/index.tsx` from the incomplete recovered mobile baseline that **does not define** `syncLayoutLocale`.

Evidence: `diagnose/ROOT_CAUSE.txt`, `diagnose/i18n.diff`, `diagnose/repro-syncLayoutLocale.txt`.

## 3. Fix (runtime 0.1.0)

1. Rebuild OTA from runtime-compatible SRC tree (includes `syncLayoutLocale`) + Bank ESS release overlays.
2. Guard: `if (typeof syncLayoutLocale === 'function') void syncLayoutLocale()`.
3. Always `console.error` in `AppErrorBoundary.componentDidCatch`.
4. Startup contract script `scripts/verify-ota-startup.py`.
5. Cleared Metro cache after a bad intermediate publish that reused the stale tree (`f65e46d0…`).

## 4. iOS export / startup smoke

- `expo export --clear` → iOS+Android **PASS** (fonts present, ~1.8MB hbc)
- Fingerprint: `syncLayoutLocale`, typeof guard, `bank.verifiedTitle`, `COMPLETION_STATES` — PASS
- Capability foundation GREEN
- Published fingerprint PASS (`mobile/published-fingerprint.txt`)

## 5. Republished canary (use this)

| Item | Value |
|---|---|
| Group | `85f648c9-73a0-4b14-9d8e-838913496a4d` |
| Runtime | `0.1.0` |
| Branch | `canary` |
| iOS | `019fd81a-629a-7289-82ce-6207924ecc10` |
| Android | `019fd81a-629a-7922-95b0-f9a502cf1c4e` |
| Message | Fix Bank ESS OTA syncLayoutLocale clean 20260806T172002Z |

**Do not use** intermediate group `f65e46d0-50ae-41c6-b4ce-d75233f87168` (Metro cache of stale tree).

## 6. Physical verification

**Agent:** no iPhone attached (`xcrun` / USB empty).  
**Owner steps (required to close the loop):**

1. Force-quit Wathefni on the canary iPhone.
2. Reopen (pulls tip `85f648c9-73a0-4b14-9d8e-838913496a4d`).
3. Confirm home launches (no “fresh start”).
4. Open **Onboarding** — completion state renders.
5. Open **Bank** — no submit; EN/AR if possible.
6. Reply with PASS/FAIL.

## Rollback of this fix

```bash
cd apps/wathefni-employee-mobile
npx eas-cli update:rollback 85f648c9-73a0-4b14-9d8e-838913496a4d \
  --message "Rollback Bank ESS OTA fix 20260806T172002Z" \
  --platform all --non-interactive
```

Or re-republish prior good group `cb2655a4-6451-4724-b321-0d20929aa838`.

## Dashboard

Unchanged this stamp (`PostHire-BRA7Ln_S.js` remains live from Phase 1B).
