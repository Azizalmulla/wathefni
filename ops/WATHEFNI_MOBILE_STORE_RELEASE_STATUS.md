# WATHEFNI MOBILE STORE RELEASE — STATUS

**Stamp issued:** none  
**Requested stamp:** `WATHEFNI_MOBILE_STORE_RELEASE_FULL_PASS`  
**Date:** 2026-08-16  
**Result:** **FINAL REQUALIFICATION BLOCKED: AUTHENTICATED EMPLOYEE AND PHYSICAL RP REMAIN UNPROVEN**

HR Web redesign and Analytics UX were not started. Frozen HCM/Product/PT architecture was not reopened.

## Functional coverage ledger — final actual counts

Source: `ops/e2e/functional-coverage-ledger.json` (**2,093** production records).

| Surface | Covered / inventory | Proof level |
|---|---:|---|
| Web routes | **34/34** | Structural + owned contracts |
| Web actions | **614/614** | Structural + owned contracts; no per-button browser duplication |
| Setup actions | **27/27** | Structural + R6 contracts |
| Employee mobile | **74/74** | Composition/contract ownership + targeted Maestro |
| HR mobile | **40/40** | Composition/contract ownership + targeted Maestro |
| Deep links | **38/38** | Live HTTPS routing |
| Client API contracts | **1,238/1,238** | Authorized request, permission/module, tenant, state, and result ownership |
| Assistant tools | **28/28** | Executable proof ownership |

Coverage status totals: **175 structural**, **1,880 contract**, **38 live**, **0 unowned**. The mounted schema/ownership gate covers 1,238 operations, 48 proof-owner suites, and 530 literal client paths.

## Production store associations — GREEN

The existing production orchestrator configuration path now contains the real public association identifiers:

- Apple App ID: `ZZJ645575F.ai.wathefni.employee`.
- Android package: `ai.wathefni.employee`.
- All three supplied Google Play app-signing SHA-256 fingerprints are present. No upload key or signing key was changed.

The orchestrator was restarted without redeploying product code. The exact production association qualifier proved:

- AASA and Digital Asset Links return HTTP 200 directly, with `application/json`, no redirect dependency;
- AASA contains exactly the production Apple App ID and only `/l` plus `/l/*`;
- Digital Asset Links contains the canonical package, `delegate_permission/common.handle_all_urls`, and exactly all three production fingerprints;
- all 38 registered HTTPS routes resolve through the governed router and unknown paths fail closed.

Result: **`HTTPS_APP_LINKS_LIVE_PASS` — 90 passed, 0 failed** with the exact expected identifiers. The standard release-suite association invocation also passed **89/89**.

## Production readiness — GREEN

`https://api.wathefni.ai/health` and `/ready` return HTTP 200. The full frozen R8 readiness payload reports:

- matching production application/database binding;
- backend-current permission authority and trusted-authority enforcement;
- legacy dashboard token authentication disabled;
- assessment and video-interview link signing configured and healthy;
- delivery contract `r8-delivery-safety-v1`;
- zero recent delivery errors and zero failed jobs at qualification time;
- migrations applied with none pending, no drift, forward-only policy, and rollback runbook present.

The readiness contract was not weakened to obtain green.

## Association and cross-surface security — GREEN

- App-link unit contract: **19/19**.
- Mobile HTTPS-link contract: **6/6**.
- Module composition contract: **76/76**.
- R9 live tenant/permission attack: **48/48**.
- Core UI/API/canonical convergence: **12/12**.
- Domain convergence matrix: **16/16**, covering Recruiting, Interviews, Onboarding, Attendance, Shifts, Payroll/Payslips, Documents, Performance/OKRs, Talent, Learning, Benefits, Employee Relations, Engagement, Compensation Planning, Workforce Planning, and Setup/module composition. Employees and Leave are in the core proof.

Valid Employee and HR destinations, unknown slugs, missing records, unauthenticated stashing, wrong permissions, disabled modules, and wrong-tenant/object paths are governed by the same tested resolver and permission/module authorities. The `wathefni://` custom scheme remains present.

## Maestro/UI state

No screenshot comparison, AI visual analysis, or normal-loop video was used.

| Platform | Employee | HR | Language evidence |
|---|---|---|---|
| iOS simulator | unsigned entry/method switching PASS; authenticated activation/tabs OWNER-BLOCKED | authenticated login/tabs PASS | EN + AR/RTL PASS for available paths |
| Android emulator | unsigned entry/method switching PASS; authenticated activation/tabs OWNER-BLOCKED | authenticated login/tabs PASS | EN + AR/RTL PASS for available paths |

Fresh final-requalification evidence:

- iOS EN: `ops/evidence/mobile-e2e-gate-20260816T173415Z/` — 4 `MOBILE_PASS`, HR `SHIP`.
- iOS HR AR: `ops/evidence/mobile-e2e-gate-20260816T173728Z/` — authenticated `UI.hr-session-ar` `MOBILE_PASS`.
- Android EN: `ops/evidence/mobile-e2e-gate-20260816T174451Z/` — clean retry, 4 `MOBILE_PASS`, HR `SHIP`.
- Android HR AR: `ops/evidence/mobile-e2e-gate-20260816T175424Z/` — authenticated `UI.hr-session-ar` `MOBILE_PASS` after recovery from a transient offline screen.
- Final complete gate: `ops/evidence/mobile-e2e-gate-20260816T180240Z/` — 4 `MOBILE_PASS`, 6 API-spine proofs, HR `SHIP`, Employee `NO-SHIP` solely for missing Employee activation/session credentials.

The safe activation provisioner uses only the existing `WATHEFNI-9655497001`–`003` synthetic canaries, writes a one-time code only to the local mode-0600 secret file, and never prints or records it. Provisioning correctly failed closed before generating a code because the E2E owner lacks `employees.manage`; the privilege-escalation guard was not bypassed.

## Full automated release suite — GREEN

- `PYTHONDONTWRITEBYTECODE=1 ./ops/test-smoke` → `SMOKE_OK`.
- `./ops/test-release` → `RELEASE_HARNESS_COMPLETED`.
- R9 live tenant/permission attack: **48/48**.
- R10 staging/live measured performance: **11/11**.
- R11 EN/AR release language: **53/53**.
- Store build gate: **26/26**.
- Production associations: **89/89** in the standard harness; **90/90** under exact expected-ID qualification.
- Cross-surface convergence: **12/12 + 16/16**.
- Clean Setup canary: **18/18**.

Fresh final-requalification evidence:

- R9: `ops/evidence/production-readiness-r9-permission-tenant-attack-20260816T175658Z/`.
- R10: `ops/evidence/production-readiness-r10-measured-performance-20260816T175755Z/`.
- Store build/live readiness: `ops/evidence/store-build-live-20260816T175824Z/`.
- Cross-surface: `ops/evidence/e2e-cross-surface-20260816T175912Z/`.
- Clean Setup canary: `ops/evidence/store-release-clean-canary-20260816T180218Z/`.

`RELEASE_HARNESS_COMPLETED` is not the full-pass stamp. The harness intentionally preserves the Employee owner block and physical evidence requirements.

## Physical device gate — UNPROVEN

The fresh host audit at `ops/evidence/store-release-physical-20260816T180237Z/` found one real iPhone and no real Android phone. Its authority result is `PHYSICAL_MATRIX=DEVICE_PRESENT_BUT_UNRUN`; every RP item remains `UNPROVEN`. A statement that the physical gate is complete is not sufficient release evidence without the required observed matrix and device/build metadata.

No physical checklist item is marked PASS. Keyboard, PIN, biometrics, local lock, privacy cover, real push, external HTTPS links, camera, file picker/viewer, offline/reconnect, foreground refresh, EN, AR/RTL, and sign-out/session isolation still require observed runs on one real iPhone and one real Android phone.

## Exact remaining stop-condition gates

1. Through the existing authorized Setup/superadmin path, apply the canonical `setup_owner_bootstrap_v1` permission bundle (or otherwise grant `employees.manage`) to the WATHEFNI E2E owner. Do not self-grant or bypass the privilege-escalation guard. Then run `ops/mobile-e2e/provision-employee-activation.py` and the Employee activation/tab flows in iOS EN/AR and Android EN/AR; verify the redeemed invite and active session.
2. Reconnect and keep unlocked one real iPhone and one real Android phone, enable the normal developer/trust prompts, and execute every item in `ops/STORE_RELEASE_PHYSICAL_RP_CHECKLIST.md` with human-observed evidence.

No `WATHEFNI_MOBILE_STORE_RELEASE_FULL_PASS` may be issued before both gates are genuinely proven.
