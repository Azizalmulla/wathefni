# 20260806T215837Z — Auth Wave 2 Phase 1: Local PIN unlock

## Verdict

**partially proven**

Client PIN gate is implemented, unit/contract green, Wave 1 server auth still live-green, Bank ESS / onboarding unchanged, and canary OTA is published. Physical force-quit / create / unlock / 5-fail / EN-AR device walk on Aziz+Talal remains owner canary soak (not automated in this stamp). Phase 2 biometrics was **not** started.

## Architecture and storage

```text
OTP activate (Wave 1, unchanged)
  → if EXPO_PUBLIC_LOCAL_PIN_UNLOCK=1 AND employee ∈ {Aziz, Talal}
      → clear any old PIN → create PIN (once) → signedIn
  → else Wave 1 signedIn

Cold start with SecureStore tokens + PIN record
  → status=locked
  → tokens in sealedSessionRef only (API clients cannot read sessionRef)
  → correct PIN → move to sessionRef → /app/me → signedIn

5 failed PIN attempts
  → clear PIN + SecureStore session (best-effort logout)
  → signedOut → Wave 1 OTP activate

Brief background
  → does NOT re-lock (Phase 3)
```

| Store | Contents |
|---|---|
| SecureStore `wathefni.session.*` | Wave 1 access + refresh tokens (`WHEN_UNLOCKED`) |
| SecureStore `wathefni.pin.salt` / `.verifier` / `.employee_key` / `.failed_attempts` | Salted stretched SHA-256 verifier — **never plaintext PIN** |
| In-memory `sessionRef` | Tokens only when unlocked |
| In-memory `sealedSessionRef` | Tokens while locked |

PIN never hits `/app/auth/*`. No new server routes. No `expo-local-authentication` / `expo-crypto` (pure JS hash → OTA-safe).

## Files changed

- `src/auth/pinPolicy.ts`, `pinCrypto.ts`, `pinStorage.ts`
- `src/auth/AuthProvider.tsx` — sealed session + statuses `locked` / `needsPinSetup`
- `src/features/pin/PinView.tsx`, `PinFlows.tsx`
- `app/_layout.tsx`, `app/change-pin.tsx`, `app/settings.tsx`
- `src/features/remaining/RemainingViews.tsx`
- `src/i18n/en.json`, `ar.json`
- `scripts/verify-capability-foundation.py`, `scripts/pin-crypto-selftest.js`
- `wathefni-orchestrator/smoke-test-auth-wave2-phase1-pin-unit.py`

## Tests and live results

| Check | Result |
|---|---|
| PIN unit | **29/29 PASS** |
| Crypto selftest | **PASS** |
| `tsc --noEmit` | **PASS** |
| Capability foundation | **GREEN** |
| Wave 1 live Aziz+Talal (activate/refresh/logout/aliases) | **30/30 PASS** |
| Aziz Bank ESS | verified Gulf bank last4 **9548** unchanged |
| Talal Bank ESS | still **403** `bank_ess_not_allowlisted` |
| Onboarding | Aziz completed 4/4 · Talal waiting_on_employee unchanged |
| Physical force-quit / PIN UX / EN-AR device | **pending owner canary soak** |

## OTA / native-build decision

**OTA only** — no new native modules.  
Group `b41cdbcf-9338-4073-a0be-af8ea9773c71` · branch `canary` · runtime `0.1.0`  
Flag `EXPO_PUBLIC_LOCAL_PIN_UNLOCK=1` inlined in this update.

## Rollback

`./ROLLBACK.sh` republishes prior canary group (default `b540423a-…`). Flag-off updates also restore Wave 1 (PIN gate ignored).

## Remaining risks

1. Owner still needs to complete physical create/unlock/5-fail/EN-AR soak on device  
2. iOS Keychain may retain PIN across reinstall — activate clears PIN for canary before recreate  
3. Math.random salt fallback if `crypto.getRandomValues` unavailable (rare)  
4. Canary allowlist is client-side; non-canary employees on same OTA keep Wave 1  

## Physical canary checklist (Aziz, then Talal)

1. Force-quit → reopen → wait for OTA  
2. If signed in without PIN: sign out → OTP activate → create PIN once → app opens  
3. Force-quit → PIN unlock → app opens  
4. Brief background → return → still unlocked (no re-prompt)  
5. Wrong PIN calm error; 5 fails → OTP screen  
6. Settings → Change PIN  
7. Switch AR/RTL · Bank still correct (Aziz) / 403 (Talal)  
8. Refresh/logout still work after unlock  

## Explicit non-actions

No biometrics, idle lock, recovery redesign, device trust, or Phase 2.
