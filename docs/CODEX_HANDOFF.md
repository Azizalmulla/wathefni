# Codex handoff

**Updated:** 2026-08-16  
**Branch:** `authority-cutover`  
**Requested stamp:** `WATHEFNI_MOBILE_STORE_RELEASE_FULL_PASS`  
**Status:** **AUTOMATED QUALIFICATION COMPLETE; OWNER VALUES, EMPLOYEE ACTIVATION, AND PHYSICAL DEVICES REMAIN**

The GitHub repository is the Wathefni source authority. This handoff continues the frozen store-release program only. It does not reopen HCM/Product/PT architecture, start HR Web redesign, or authorize new product work.

## Current truth

- Functional coverage ledger: **2,093/2,093 owned**, with zero gaps. Client API contracts are **1,238/1,238** and assistant tools are **28/28**.
- Mounted API ownership: **9/9** contract checks, covering 1,238 operations, 48 executable proof owners, and 530 literal production client paths.
- Private API fail-closed probe: **1,196/1,196** staging operations returned the required 401/403 without a principal.
- Cross-surface convergence: **18/18** canonical employee/leave/module checks plus **16/16** domain suites.
- Production `https://api.wathefni.ai/ready`: HTTP 200 and `status=ready`; environment binding, trusted authority, link signing, delivery error count, failed jobs, migrations, drift, forward-only policy, and rollback runbook match the frozen R8 contract.
- Release suite: `./ops/test-smoke` reached `SMOKE_OK`; `./ops/test-release` reached `RELEASE_HARNESS_COMPLETED` after R9 **48/48**, R10 **11/11**, R11 **53/53**, store-build **26/26**, cross-surface **34/34**, and clean Setup canary **18/18**.
- Maestro: authenticated HR EN and AR paths passed on iOS and Android. Employee unsigned EN and AR paths passed on both platforms. Authenticated Employee activation/tabs remain blocked because no valid Employee activation phone/code was available.
- Production HTTPS link routing is **84/84**. AASA and Digital Asset Links are intentionally owner-blocked because their real production identifiers are not configured.
- Physical gate: **UNPROVEN**. The corrected host audit saw no connected iPhone or Android phone. No physical PASS is claimed.

## Remaining inputs and gates

1. Apple Team ID: configure `WATHEFNI_IOS_APP_ID=<10-character Team ID>.ai.wathefni.employee`.
2. Google Play App Signing SHA-256: configure `WATHEFNI_ANDROID_SHA256_CERTS=<colon-separated SHA-256>` using the **App signing key certificate**, not the upload key.
3. Employee mobile: place a live, unconsumed activation phone/code in the local secret file as `MOBILE_E2E_EMPLOYEE_PHONE` and `MOBILE_E2E_EMPLOYEE_CODE`; add `MOBILE_E2E_EMPLOYEE_BEARER` when an employee API reconciliation token is available.
4. Re-run the iOS and Android Employee activation/tabs flows, then execute the physical RP checklist on one real iPhone and one real Android phone.

Secrets belong in `~/.config/wathefni/e2e.env` with mode `0600`, never in Git. Production association values belong in the `wathefni-orchestrator.service` environment, followed by `daemon-reload`, restart, and the association qualifier.

## Commands

```bash
PYTHONDONTWRITEBYTECODE=1 ./ops/test-smoke
./ops/test-release

MOBILE_E2E_PLATFORM=ios MOBILE_E2E_LOCALE=en \
  wathefni-orchestrator/.venv/bin/python ops/mobile-e2e/run-release-gate.py
MOBILE_E2E_PLATFORM=android MOBILE_E2E_LOCALE=en \
  wathefni-orchestrator/.venv/bin/python ops/mobile-e2e/run-release-gate.py

WATHEFNI_APP_LINK_BASE=https://api.wathefni.ai \
  wathefni-orchestrator/.venv/bin/python ops/e2e/qualify-https-app-links.py
./ops/qualify-physical-device-matrix.sh
```

## Latest evidence

- Full automated mobile gate: `ops/evidence/mobile-e2e-gate-20260816T142419Z/`
- iOS EN: `ops/evidence/mobile-e2e-gate-20260816T132240Z/`
- iOS HR AR: `ops/evidence/mobile-e2e-gate-20260816T133421Z/`
- iOS unsigned AR: `ops/evidence/mobile-e2e-gate-20260816T133658Z/`
- Android EN: `ops/evidence/mobile-e2e-gate-20260816T133927Z/`
- Android HR AR: `ops/evidence/mobile-e2e-gate-20260816T134145Z/`
- Android unsigned AR, hardened release artifact: `ops/evidence/mobile-e2e-gate-20260816T135230Z/`
- R9: `ops/evidence/production-readiness-r9-permission-tenant-attack-20260816T142034Z/`
- R10: `ops/evidence/production-readiness-r10-measured-performance-20260816T142113Z/`
- Store build/live readiness: `ops/evidence/store-build-live-20260816T142129Z/`
- Android local release manifest: `ops/evidence/android-release-manifest-20260816T141100Z/`
- Cross-surface: `ops/evidence/e2e-cross-surface-20260816T142156Z/`
- Clean Setup canary: `ops/evidence/store-release-clean-canary-20260816T142354Z/`
- Corrected physical audit: `ops/evidence/store-release-physical-20260816T142417Z/`

Status authority: `ops/WATHEFNI_MOBILE_STORE_RELEASE_STATUS.md`. Physical procedure: `ops/STORE_RELEASE_PHYSICAL_RP_CHECKLIST.md`.

## Do not reopen

Preserve Waves 1–6, R2–R11, R5A–R5J, PT1–PT7, and accepted freeze amendments. Do not weaken readiness or tenant isolation. Do not add fake/demo production data. Do not start HR Web redesign, Analytics UX, or new release work before this store closure is explicitly resolved.
