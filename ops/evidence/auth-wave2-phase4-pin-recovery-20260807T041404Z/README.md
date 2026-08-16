# Auth Wave 2 Phase 4 — Simple PIN recovery

**Stamp:** `20260807T041404Z`  
**Verdict:** **partially proven** — unit green; physical matrix pending  
**Phase 5:** not started

## Scope (small)

- **Forgot PIN?** on unlock PIN screens (cold-start + auto-lock overlay)
- Confirmation: *You'll need to activate the app again and create a new PIN.*
- On confirm / on **5 failed PIN attempts**: clear local PIN · disable biometric preference · clear local session · return to phone + activation code
- After activation: create new PIN · optional Face ID again
- No new backend auth routes · network/server errors do **not** trigger this reset

## Implementation

| Piece | Detail |
|---|---|
| API | `recoverPinByReactivation()` (in-flight guard) → `clearLocalAuthMaterial()` + `signedOut` |
| Clears | PIN verifier/salt · biometric preference · SecureStore session · query cache |
| 5-fail | `unlockWithPin` · `changeLocalPin` · overlay `verifyPin` lockout |
| UI | `UnlockPinFlow` Alert → EN/AR · RTL via existing PinView |
| Existing logout | Best-effort `POST /app/auth/logout` only (already existed) |

## OTA

| Field | Value |
|---|---|
| Group | `af0c0998-d41b-4f68-a2a2-3fabc06537c0` |
| Runtime | `0.1.0` |
| Branch | `canary` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/af0c0998-d41b-4f68-a2a2-3fabc06537c0 |
| Prior | `9a9a11be-dc9a-4e01-a1ec-f6f98bc5e2de` |

## Tests

| Suite | Result |
|---|---|
| Phase 4 unit | **24/24** |
| Phase 3 overlay unit | **61/61** |
| `tsc --noEmit` | PASS |

## Physical matrix

1. Force-quit → pull OTA
2. Locked PIN → **Forgot PIN?** → confirm → activation screen
3. Old PIN / Face ID must not unlock
4. Activate → create new PIN → optional Face ID → unlock works
5. Enter wrong PIN ×5 → same clean reset (no duplicate clears / random mid-session logout from network)

## Rollback

`./ROLLBACK.sh` republishes prior canary group message with recover UI removed by republishing previous OTA env from `9a9a11be-…` source, or disable via republish of nav-preserve build.

```bash
./ROLLBACK.sh
```
