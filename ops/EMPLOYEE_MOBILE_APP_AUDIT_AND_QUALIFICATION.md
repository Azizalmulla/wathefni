# Employee Mobile App — Audit & Production Qualification

**Stamp:** `20260805T014204Z`  
**App:** `apps/wathefni-employee-mobile` (Expo 51 / RN 0.74 · `ai.wathefni.employee`)  
**Scope:** Talal canary only · no redesign · no payroll money · no hiring/admin  
**Evidence:** `ops/evidence/employee-mobile-app-qual-20260805T014204Z/`

## Production boundary (preserved)

| Gate | Prod value |
|---|---|
| `WATHEFNI_EMPLOYEE_APP` | `on` |
| `WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST` | `on` |
| `WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST` | `WATHEFNI-96550252254` (Talal) |
| ESS V5 | `on` + `SYNTHETIC_ONLY=on` · real allowlist Talal · bank allowlist **empty** |
| `company_modules.employee_app` | enabled for `WATHEFNI` |
| Payslips feature | **disabled** (`feature_not_available`) |

## Route / flow PASS/FAIL

| Flow | Verdict | Notes |
|---|---|---|
| Login / activation (phone + HR code) | **PASS** (contract) | Implemented; gated by allowlist on activate |
| Session refresh / expiry | **PASS** | AuthProvider 401→refresh; invalid token → 401 |
| Logout | **PASS** (contract) | `/app/auth/logout` + push unregister |
| Non-allowlisted denial | **PASS** | Backend 403 `employee_app_not_allowlisted`; client now maps dedicated access state |
| Home | **PASS** | Capability-driven cards/actions; preview EN/AR watermark **removed** |
| Profile / employment details | **PASS** | `/app/me` + `/app/profile` 200 for Talal |
| Attendance (view) | **PASS** | `/app/attendance` 200; clocking mutations not in app (view history) |
| Leave balance / request / cancel | **PASS** | `/app/leave` 200; types from backend; request/cancel screens gated |
| Shifts today / upcoming | **PASS** | both endpoints 200 |
| Onboarding tasks + upload | **PASS** | `/app/onboarding` 200; upload path capability-enforced |
| Documents / compliance journey | **PASS** | `/app/documents` 200; renew upload; no separate compliance_actions UI (reserved) |
| Notifications / alerts | **PASS** | `/app/notifications` 200; mark-read; production push registration **off** by EAS profile |
| Settings (locale, push, deletion) | **PASS** (with note) | Locale switch + RTL restart alert; push gated; deletion request to HR |
| English / Arabic copy | **PASS** | Keysets match; capability foundation GREEN |
| RTL native flip | **PASS WITH FINDINGS** | `forceRTL` + user alert to restart; no auto-reload (no `expo-updates`) |
| Loading / empty / error states | **PASS** (code) | Home/feature/access shells present |
| Offline | **PASS** (contract) | `network_error` → offline access state |
| Tenant / identity authority | **PASS** | Session-bound `/app/*`; client must not send `employee_key` |
| Payroll / payslips | **PASS (blocked by design)** | Feature disabled; no money UI |
| Hiring / admin workflows | **PASS (absent)** | Not in employee app |
| iOS build readiness | **FAIL (store)** | See blockers |
| Android build readiness | **FAIL (store)** | See blockers |

## What already works

- Thin `/app/*` client with SecureStore session, capability-driven tabs, EN/AR i18n
- Talal production canary: mint session → all core module GETs **200**; payslips disabled; non-allowlisted denied
- Capability foundation script **GREEN**; E360 freeze regression **57/57**
- Account deletion request path present for App Store policy
- Production push forced off (`EXPO_PUBLIC_PUSH_REGISTRATION_ENABLED=0`)

## Broken / incomplete / stale

| Item | Class |
|---|---|
| EAS `projectId` = `REPLACE_WITH_EAS_PROJECT_ID` | Store / build blocker |
| No app icon / splash assets | Store blocker |
| Privacy policy URL / publish | Store blocker (`PRIVACY.md` draft) |
| Expo SDK 51 vs current tooling; no physical TestFlight yet | Readiness |
| Android FCM + notification icon before push on | Android push |
| No crash reporting / source maps | Ops |
| `docs/phase9a2-preview/` documents removed preview route | Stale docs |
| Unbounded notification/leave/document lists | Perf debt |
| Locale not synced to backend (`change_locale` unused) | Incomplete (client-only) |
| Generic `smoke-test-employee-app.py` fails under prod allowlist (synthetic EMPAPPTESTCO) | Harness drift — use Talal canary smoke instead |

## Fixes made (low-risk, canary client)

1. Map `employee_app_not_allowlisted` → dedicated access state + EN/AR copy (no retry loop)
2. Remove Home `previewLocale` EN/AR leftover watermark
3. Alert when native RTL direction flips (restart required)
4. CAPABILITIES.md: documents may include `upload_document`; payslips explicitly no money authority
5. Added `ops/smoke-test-employee-mobile-talal-canary.py` for Talal-scoped prod API probe

**Deploy posture:** client fixes are in-repo for the next internal EAS preview/dev-client build. No backend contract, allowlist, or permission change. No store submit.

## Remaining blockers (store / broad GA)

1. Real EAS project + logged-in owner account  
2. Icon + splash  
3. Published privacy + support URLs  
4. Signed physical-device build + device matrix (a11y / camera / upload)  
5. Crash reporting  
6. SDK upgrade plan (51→modern) before relying on current Expo Go  
7. Broad allowlist expansion — **NO-GO** without owner change-control  

## iOS readiness

| Item | Status |
|---|---|
| Bundle ID `ai.wathefni.employee` | Set |
| EAS production profile → `api.wathefni.ai` | Set |
| Dev client profile | Present |
| TestFlight internal | **Blocked** (EAS projectId, assets, privacy) |
| App Store public | **NO-GO** |

## Android readiness

| Item | Status |
|---|---|
| Package `ai.wathefni.employee` | Set |
| EAS profiles | Present |
| FCM V1 / notification icon | **Missing** for push |
| Play internal testing | **Blocked** (same as iOS + FCM) |
| Play public | **NO-GO** |

## Canary test plan (Talal)

1. HR issues activation code for `WATHEFNI-96550252254` from dashboard (or use existing session).  
2. Build: `eas build --profile preview` (staging) then `production` (api.wathefni.ai) once EAS projectId is real.  
3. Install on one iPhone + one Android; activate as Talal only.  
4. Verify: Home cards match enabled modules; open Attendance / Leave / Shifts / Onboarding / Documents / Notifications.  
5. Leave: request + cancel (if policy allows); confirm no payslip entry.  
6. Upload one onboarding/doc renew; confirm HR sees file.  
7. Toggle AR↔EN; confirm restart alert; relaunch and check RTL.  
8. Deny notification permission; confirm inbox still works.  
9. Airplane mode → offline state → retry.  
10. Sign out; confirm non-Talal phone+code gets allowlisted denial copy (if attempted).  
11. Backend: `python3 ops/smoke-test-employee-mobile-talal-canary.py` on VPS with systemd employee-app env exported.

## GO / NO-GO

| Decision | Result |
|---|---|
| Continue Talal internal canary (API + next signed build) | **GO** |
| Store submission (App Store / Play) | **NO-GO** |
| Broad employee-app GA / allowlist expansion | **NO-GO** |
| Payroll / money in app | **NO-GO** |

## Rollback

Client-only diffs — revert the employee-mobile commit/files listed above.  
Backend flags unchanged; Talal allowlist unchanged.  
No production web/orchestrator deploy in this stamp.
