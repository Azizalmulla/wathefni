# 20260806T214259Z — Auth Wave 2 Phase 0: Wave 1 login freeze

## Verdict

**ready_for_phase_1**

Phase 0 only. No PIN, biometrics, idle lock, recovery, device trust, or new native deps.

## Frozen auth contract

Canonical document: `ops/AUTH_WAVE1_FROZEN_CONTRACT.md` (copy in `docs/`)

Locks:

- OTP activate / request-code / refresh / logout
- New-device session revocation (`reactivated_via_invite`)
- Kuwait 8↔965 phone aliases
- `session_epoch` kill switch
- SecureStore `WHEN_UNLOCKED` token handling
- Expiry / retry / failure matrix (24h invite · 5 attempts · 60s resend · 7d access · 180d refresh)
- Binding rule: future PIN unlocks existing local session only — never a second server auth system

UX rules recorded for later phases (not implemented):

- First login: OTP once → create PIN  
- Normal return: open app → PIN → app opens  
- Later: Face ID first, PIN fallback  

## Tests added

| Test | Result |
|---|---|
| `wathefni-orchestrator/smoke-test-auth-wave1-freeze-unit.py` | **PASS** 35/35 (constants, routes, SecureStore, non-actions) |
| VPS Kuwait alias import | **ALIAS_PASS** |
| `smoke-test-employee-app.py` extended | HTTP refresh · local-8 activate · logout · request-code generic · `reactivated_via_invite` (staging harness; not re-run on prod DB) |

## Live verification (Aziz + Talal)

`ops-prove-auth-wave1-freeze-live.py` → **PASS** 30/30

Per canary: local-8 activate → `/app/me` reopen → refresh (old access 401) → new-device re-activate (`reactivated_via_invite`) → logout (access+refresh 401) → request-code generic → canary session restored.

Bank ESS + onboarding untouched:

| Employee | Bank | Onboarding |
|---|---|---|
| Aziz | verified Gulf bank last4 **9548** · fp `0f349ce848ab5e4b` unchanged | `completed` 4/4 owner `none` |
| Talal | still `403 bank_ess_not_allowlisted` | `waiting_on_employee` unchanged |

## Evidence

- `docs/AUTH_WAVE1_FROZEN_CONTRACT.md`
- `prove/unit.txt` · `prove/live.txt` · `prove/live.json`
- `prove/ops-prove-auth-wave1-freeze-live.py` · `prove/smoke-test-auth-wave1-freeze-unit.py`

## Remaining risks (do not block Phase 1 start)

1. OTP delivery still uses outbound ladder (WhatsApp) — ops channel reliability, not Wave 1 contract drift  
2. Physical-device SecureStore reopen not re-tapped in this stamp (API reopen equivalent proven; device path unchanged)  
3. Staging harness extensions need a staging DB run before relying on CI green for those new cases  
4. Phase 1 must not treat PIN as server auth or change TTLs / revoke reasons / alias rules  

## Explicit non-actions

Phase 1 was **not** started. No auth product code beyond docs/tests/prove scripts.
