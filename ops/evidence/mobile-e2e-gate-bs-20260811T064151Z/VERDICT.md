# Mobile E2E release gate — 20260811T064151Z

**Suite:** `bs-smoke`
**Evidence:** `ops/evidence/mobile-e2e-gate-bs-20260811T064151Z`

## Rule

**API PASS ≠ MOBILE PASS.** MOBILE_PASS only when Maestro opened the app on a real simulator/device.

## Counts

| Verdict | Count |
| --- | ---: |
| API_SPINE | 1 |
| BLOCKED | 1 |
| FAIL | 6 |
| MOBILE_PASS | 1 |

## SHIP / NO-SHIP

| Product | Verdict |
| --- | --- |
| HR (unified `/hr`) | **NO-SHIP** |
| Employee | **NO-SHIP** |

Reason: UI FAIL count=4

## Host blockers

- `java_runtime_missing_for_maestro`
- `ios_simulator_runtime_missing`
- `adb_missing`
- `disk_free_lt_9gb_for_ios_runtime`
- `no_executable_ui_target`

## Matrix

- `UI.00-launch-unsigned` · **MOBILE_PASS** — BrowserStack iPhone 15 iOS 17.3 status=passed duration=28.254 dashboard=https://app-automate.browserstack.com/dashboard/v2/builds/2d5ce7f652ba62a83bc539becd3aa9df55cc5a60
- `UI.01-hr-login` · **FAIL** — BrowserStack iPhone 15 iOS 17.3 status=failed duration=187.074 dashboard=https://app-automate.browserstack.com/dashboard/v2/builds/2d5ce7f652ba62a83bc539becd3aa9df55cc5a60
- `UI.02-hr-tabs` · **FAIL** — BrowserStack iPhone 15 iOS 17.3 status=failed duration=194.211 dashboard=https://app-automate.browserstack.com/dashboard/v2/builds/2d5ce7f652ba62a83bc539becd3aa9df55cc5a60
- `UI.03-hr-leave-approve` · **FAIL** — BrowserStack iPhone 15 iOS 17.3 status=failed duration=185.5 dashboard=https://app-automate.browserstack.com/dashboard/v2/builds/2d5ce7f652ba62a83bc539becd3aa9df55cc5a60
- `UI.04-hr-leave-reject` · **FAIL** — BrowserStack iPhone 15 iOS 17.3 status=failed duration=195.766 dashboard=https://app-automate.browserstack.com/dashboard/v2/builds/2d5ce7f652ba62a83bc539becd3aa9df55cc5a60
- `API.health` · **API_SPINE** — GET /healthz → 200
- `API.hr.login` · **FAIL** — HR login failed → 500 Internal Server Error
- `API.employee.session` · **BLOCKED** — Set MOBILE_E2E_EMPLOYEE_BEARER (from activate) for employee API spine
- `API.leave.reconcile` · **FAIL** — {"approve": "cancelled", "reject_reason_persisted": true, "reject": "cancelled"}
