# STATUS — Auth Wave 2 activation restore

| Field | Value |
| --- | --- |
| Stamp | `20260809T043924Z` |
| Verdict | **PASS** |
| OTA | `f226bdf5-d48e-49ef-b172-7c3672a0723e` |
| Rollback | `cf1cd9a5-39fc-4e8f-a603-fb6679b90b63` (Bank hierarchy) |
| Runtime | `0.1.0` · canary · JS-only |
| Dist proof | `pin-unlock-effective:on` · `bio-unlock-effective:on` · `al-lock-effective:on` in HBC |

## Root fix
Visual OTAs published without baking `EXPO_PUBLIC_LOCAL_*=1`, and masters previously **failed closed** when unset (`=== '1'` only). That disabled PIN/Face ID/auto-lock for everyone, including Aziz.

## How OTA env persistence is now guaranteed
1. **EAS production env** — `EXPO_PUBLIC_LOCAL_PIN_UNLOCK/BIOMETRIC_UNLOCK/AUTO_LOCK(/_BIOMETRIC)=1` created on the project
2. **`app.config.js`** — forces the same defaults when unset before Metro runs
3. **`.env.example` + local `.env`** — documented; Expo loads `.env` when present
4. **`eas.json` `build.production.env`** — native build parity
5. **`scripts/publish-canary-ota.sh`** — always `--environment production` + preflight/dist verify
6. **Fail-open masters** — unset/empty → ON; only explicit `0` disables (so a missed env cannot dark-ship again)

## Hardcoded employee gates
**Removed** from `pinPolicy.ts`, `biometricPolicy.ts`, `autoLockPolicy.ts`.  
PIN / biometric / auto-lock apply to any signed-in Employee App session when masters are on; hardware/enrollment checks unchanged.

## Preserved
Activation → PIN enroll → Face ID opt-in → biometric→PIN fallback → auto-lock overlay → recovery / capability checks.
