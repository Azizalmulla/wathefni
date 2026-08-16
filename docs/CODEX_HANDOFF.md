# Codex handoff

**Updated:** 2026-08-16  
**Branch:** `authority-cutover`  
**Requested stamp:** `WATHEFNI_MOBILE_STORE_RELEASE_FULL_PASS`  
**Status:** **ALL AUTOMATABLE RELEASE GATES GREEN; EMPLOYEE OWNER GRANT AND PHYSICAL RP REMAIN**

The GitHub repository is the Wathefni source authority. Continue only the frozen mobile store-release closure. Do not reopen HCM/Product/PT architecture, start HR Web/Analytics redesign, or add product scope.

## Current truth

- Functional ledger: **2,093/2,093 owned**, zero gaps. Client API contracts are **1,238/1,238**; assistant tools are **28/28**.
- Production associations: exact Apple App ID and all three Google Play app-signing fingerprints are configured through the existing orchestrator environment. Exact live qualification passed **90/90**; the standard release gate passed **89/89**.
- Production readiness: `/health` and `/ready` are HTTP 200; the full frozen R8 environment, permission authority, link-signing, delivery, error/failed-job, and migration dimensions are green without weakening.
- Security/convergence: R9 live tenant/permission attack **48/48**; core convergence **12/12**; domain matrix **16/16**.
- Release suite: `./ops/test-smoke` reached `SMOKE_OK`; `./ops/test-release` reached `RELEASE_HARNESS_COMPLETED` after R10 **11/11**, R11 **53/53**, store build **26/26**, and clean Setup canary **18/18**.
- Maestro: authenticated HR EN and AR passed on iOS and Android. Employee unsigned EN paths passed on both platforms; authenticated Employee activation/tabs are owner-blocked because the WATHEFNI E2E owner lacks `employees.manage`.
- Physical RP: **UNPROVEN**. A real iPhone was detected and accepted the signed Maestro XCTest runner, but the driver tunnel did not become ready before it disconnected. No real Android phone was connected. No physical PASS is claimed.

## Exact remaining actions

1. Use the existing authorized Setup/superadmin authority to apply `setup_owner_bootstrap_v1` (or grant `employees.manage`) to the WATHEFNI E2E owner. Do not bypass the self-grant guard.
2. Run the safe synthetic-canary provisioner. It writes the one-time code only to `~/.config/wathefni/e2e.env` with mode `0600` and never prints it:

   ```bash
   wathefni-orchestrator/.venv/bin/python ops/mobile-e2e/provision-employee-activation.py
   ```

3. Run authenticated Employee activation/tabs on iOS EN/AR and Android EN/AR, then verify the redeemed invite and active Employee session with `--verify-only`.
4. Connect and keep unlocked one real iPhone and one real Android phone, accept normal developer/trust prompts, and execute every item in `ops/STORE_RELEASE_PHYSICAL_RP_CHECKLIST.md` with observed evidence.

Secrets remain only in the local mode-0600 file. Never commit activation codes, passwords, bearer tokens, private keys, or `.env` files.

## Commands

```bash
PYTHONDONTWRITEBYTECODE=1 ./ops/test-smoke
./ops/test-release

MOBILE_E2E_PLATFORM=ios MOBILE_E2E_LOCALE=en \
  wathefni-orchestrator/.venv/bin/python ops/mobile-e2e/run-release-gate.py
MOBILE_E2E_PLATFORM=android MOBILE_E2E_LOCALE=en \
  wathefni-orchestrator/.venv/bin/python ops/mobile-e2e/run-release-gate.py

WATHEFNI_APP_LINK_BASE=https://api.wathefni.ai \
WATHEFNI_EXPECTED_IOS_APP_ID=ZZJ645575F.ai.wathefni.employee \
WATHEFNI_EXPECTED_ANDROID_SHA256_CERTS='<three comma-separated Play app-signing fingerprints>' \
  wathefni-orchestrator/.venv/bin/python ops/e2e/qualify-https-app-links.py

./ops/qualify-physical-device-matrix.sh
```

## Latest evidence

- Exact association deployment/qualification: `ops/evidence/store-release-associations-20260816T155815Z/REPORT.md`.
- iOS EN: `ops/evidence/mobile-e2e-gate-20260816T163249Z/`.
- iOS HR AR: `ops/evidence/mobile-e2e-gate-20260816T164450Z/`.
- Android EN: `ops/evidence/mobile-e2e-gate-20260816T164944Z/`.
- Android HR AR: `ops/evidence/mobile-e2e-gate-20260816T165215Z/`.
- Full mobile gate: `ops/evidence/mobile-e2e-gate-20260816T170015Z/`.
- R9: `ops/evidence/production-readiness-r9-permission-tenant-attack-20260816T165423Z/`.
- R10: `ops/evidence/production-readiness-r10-measured-performance-20260816T165531Z/`.
- Store build/live readiness: `ops/evidence/store-build-live-20260816T165637Z/`.
- Cross-surface: `ops/evidence/e2e-cross-surface-20260816T165747Z/`.
- Clean Setup canary: `ops/evidence/store-release-clean-canary-20260816T165952Z/`.
- Physical host audit: `ops/evidence/store-release-physical-20260816T170013Z/PHYSICAL_MATRIX.md`.

Status authority: `ops/WATHEFNI_MOBILE_STORE_RELEASE_STATUS.md`. Physical procedure: `ops/STORE_RELEASE_PHYSICAL_RP_CHECKLIST.md`.

## Do not reopen

Preserve Waves 1–6, R2–R11, R5A–R5J, PT1–PT7, and accepted freeze amendments. Do not weaken readiness, tenant isolation, permission/module composition, or production-data rules. Do not start HR Web redesign, Analytics UX, or unrelated release work.
