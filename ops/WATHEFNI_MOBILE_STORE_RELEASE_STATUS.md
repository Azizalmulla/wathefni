# WATHEFNI MOBILE STORE RELEASE — STATUS

**Stamp issued:** none  
**Requested stamp:** `WATHEFNI_MOBILE_STORE_RELEASE_FULL_PASS`  
**Date:** 2026-08-16  
**Result:** **AUTOMATABLE WORK GREEN; OWNER/PHYSICAL GATES REMAIN**

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
| Client API contracts | **1,238/1,238** | Five-dimensional ownership: authorized request, permission/module, tenant, state, result |
| Assistant tools | **28/28** | Executable proof ownership |

Coverage status totals: **175 structural**, **1,880 contract**, **38 live**, **0 unowned**.

API checks:

- Mounted schema/ownership gate: **9 passed, 0 failed**; 1,238 operations, 48 proof-owner suites, 530 literal client paths.
- Private fail-closed staging probe: **1,196 passed, 0 failed**, scoped only to operations carrying canonical private-auth dependencies.
- Assistant onboarding tools: **28/28**.

## Production readiness — GREEN

`https://api.wathefni.ai/ready` returns HTTP 200 with `status=ready` and the full frozen R8 dimensions:

- production application/database binding matches;
- backend-current permission authority and trusted-authority enforcement;
- legacy dashboard token auth disabled;
- assessment and video-interview link signing configured and healthy;
- delivery contract `r8-delivery-safety-v1`;
- zero recent delivery errors and zero failed jobs at qualification time;
- migrations healthy, no pending migrations, no drift, forward-only policy, and rollback runbook.

The readiness contract was not weakened to obtain green.

## Maestro/UI state

No screenshots, AI visual analysis, or normal-loop video were used.

| Platform | Employee | HR | Language evidence |
|---|---|---|---|
| iOS simulator | unsigned entry/method switching PASS; authenticated activation/tabs BLOCKED | authenticated login/tabs PASS | EN + AR/RTL PASS for available paths |
| Android emulator | unsigned entry/method switching PASS; authenticated activation/tabs BLOCKED | authenticated login/tabs PASS | EN + AR/RTL PASS for available paths |

Latest complete gate: `ops/evidence/mobile-e2e-gate-20260816T142419Z/` — 4 `MOBILE_PASS`, 6 API spine checks, one honest Employee-session block; HR `SHIP`, Employee `NO-SHIP` solely because activation credentials were absent.

The release runner now maps `MOBILE_E2E_EMPLOYEE_PHONE/CODE` before flow selection, so providing those values unlocks the Employee path directly.

## Cross-surface convergence — GREEN

- Core canonical convergence: **18 passed, 0 failed**.
- Domain matrix: **16 passed, 0 failed** across Recruiting, Interviews, Onboarding, Attendance, Shifts, Payroll/Payslips, Documents, Performance/OKRs, Talent, Learning, Benefits, Employee Relations, Engagement, Compensation Planning, Workforce Planning, and Setup/module composition.
- Employees and Leave are included in the 18-check core convergence proof.

Evidence: `ops/evidence/e2e-cross-surface-20260816T142156Z/`.

## Full release suite — GREEN within honest blocked-gate semantics

- `./ops/test-smoke` → `SMOKE_OK`.
- `./ops/test-release` → `RELEASE_HARNESS_COMPLETED`.
- R9 tenant/permission attack: **48/48**.
- R10 measured staging/live performance: **11/11**; live `/health` and `/ready` within budget.
- R11 EN/AR release language: **53/53**.
- Store build gate: **26/26**.
- Clean Setup canary: **18/18**.
- Final Android release manifest: backup disabled, cleartext disabled, no debug/development scheme, no overlay/microphone/legacy-storage permissions, and only the intended Wathefni scheme + App Link host.

Native manifest evidence: `ops/evidence/android-release-manifest-20260816T141100Z/`.

`RELEASE_HARNESS_COMPLETED` is not the full-pass stamp: the harness preserves exit code 2 as an explicit owner/device block for association, Employee activation, and physical-device gates.

## Owner-dependent association values

### Apple

1. Sign in at <https://developer.apple.com/account>.
2. Open **Membership details** and copy the 10-character **Team ID**.
3. Form `TEAMID.ai.wathefni.employee` and configure it as `WATHEFNI_IOS_APP_ID` in the production `wathefni-orchestrator.service` environment.

Apple reference: <https://developer.apple.com/help/glossary/team-id/>.

### Android

1. Open Play Console and select Wathefni.
2. Go to **Protected with Play → Play Store distribution → Go to Play app signing**.
3. In **App signing key certificate**, copy **SHA-256 certificate fingerprint**. Do not use the upload-key fingerprint.
4. Configure it as `WATHEFNI_ANDROID_SHA256_CERTS` in the production `wathefni-orchestrator.service` environment. Multiple active fingerprints are comma-separated.

Google reference: <https://support.google.com/googleplay/android-developer/answer/9842756?hl=en>.

Shortest production configuration path:

```ini
# sudo systemctl edit wathefni-orchestrator.service
[Service]
Environment="WATHEFNI_IOS_APP_ID=TEAMID.ai.wathefni.employee"
Environment="WATHEFNI_ANDROID_SHA256_CERTS=AA:BB:...:FF"
```

Then run `sudo systemctl daemon-reload`, restart `wathefni-orchestrator.service`, and qualify:

```bash
WATHEFNI_APP_LINK_BASE=https://api.wathefni.ai \
  wathefni-orchestrator/.venv/bin/python ops/e2e/qualify-https-app-links.py
```

Current live result: **84 passed, 0 failed, exit 2 OWNER_BLOCKED**. AASA is valid JSON with empty `details`; assetlinks is valid JSON `[]`. After configuration the qualifier requires the exact production bundle suffix and a valid 32-byte SHA-256 fingerprint before returning 0.

## Remaining stop-condition gates

1. Add valid, unconsumed Employee activation credentials to `~/.config/wathefni/e2e.env` (mode 0600), rerun Employee activation/tabs on iOS and Android, and provide an Employee bearer for the five-check employee API spine if available.
2. Provision both association values and obtain qualifier exit 0 with non-empty AASA/assetlinks.
3. Execute `ops/STORE_RELEASE_PHYSICAL_RP_CHECKLIST.md` on one real iPhone and one real Android phone.

No `WATHEFNI_MOBILE_STORE_RELEASE_FULL_PASS` may be issued before all three are proven.
