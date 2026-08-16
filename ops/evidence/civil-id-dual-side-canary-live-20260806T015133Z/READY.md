# Civil ID dual-side canary — READY for mobile live test

**Stamp:** `20260806T015133Z`  
**Status:** READY

## Proven on production

| Check | Result |
|---|---|
| Backend dual-side deployed + orchestrator active | PASS |
| Flags `DUAL_SIDE=on` · companies WATHEFNI · allowlist Aziz | PASS |
| Disposable item `civil_id_dual_side_canary` created | PASS |
| Employee projection: canary in `your_actions` | PASS |
| Actions `upload_front` + `upload_back` | PASS |
| Real `civil_id` still `accepted` | PASS |
| Civil ID SHA unchanged `fe98f7d9…0bb7` | PASS |
| Real Civil ID projection `legacy_single` (no dual demand) | PASS |
| Canary OTA published (Front/Back UX) | PASS |

## OTA

| Field | Value |
|---|---|
| Branch / runtime | `canary` / `0.1.0` |
| Update group | `968adf2a-135f-4cae-b4cc-7136f74628de` |
| iOS | `019fd4c5-ec4d-7240-a67b-c4ba342146e1` |
| Android | `019fd4c5-ec4d-72c7-a9e7-72ae11b2fc07` |
| Message | Civil ID dual-side Front/Back slots 20260806T015133Z |

## Owner mobile steps

1. Force-close / reopen Wathefni (pull canary OTA).
2. Onboarding → **CANARY ONLY — Civil ID front & back**.
3. Upload **Front**, then **Back** (camera or library).
4. Confirm item stays incomplete until both sides; then moves to review.
5. Do **not** use the real accepted Civil ID card for this test.

## Rollback

```bash
# Backend
/opt/wathefni/backups/production-pre-civil-id-dual-side-20260806T015133Z/ROLLBACK.sh
# Optional canary cleanup only
cd /opt/wathefni/orchestrator && source postgres env… && .venv/bin/python ops-aziz-civil-id-dual-side-canary.py cleanup
# OTA
cd apps/wathefni-employee-mobile
npx eas-cli update:rollback 968adf2a-135f-4cae-b4cc-7136f74628de --platform all --non-interactive
```
