# Mobile E2E release gate — 20260811T054700Z

**Suite:** `bs-smoke`
**Evidence:** `ops/evidence/mobile-e2e-gate-bs-20260811T054700Z`

## Rule

**API PASS ≠ MOBILE PASS.** MOBILE_PASS only when Maestro opened the app on a real simulator/device.

## Counts

| Verdict | Count |
| --- | ---: |
| API_SPINE | 1 |
| BLOCKED | 2 |
| MOBILE_PASS | 2 |

## SHIP / NO-SHIP

| Product | Verdict |
| --- | --- |
| HR (unified `/hr`) | **SHIP** |
| Employee | **SHIP** |

Reason: Smoke UI MOBILE_PASS with no FAIL — canary-only; broad release still needs full matrix · BS https://app-automate.browserstack.com/dashboard/v2/builds/235b7b7b50635425bd819d81174ff35944173857

## Host blockers

- `java_runtime_missing_for_maestro`
- `ios_simulator_runtime_missing`
- `adb_missing`
- `disk_free_lt_9gb_for_ios_runtime`
- `no_executable_ui_target`

## Matrix

- `UI.browserstack.sessions` · **MOBILE_PASS** — BrowserStack real-device sessions passed=1 dashboard=https://app-automate.browserstack.com/dashboard/v2/builds/235b7b7b50635425bd819d81174ff35944173857
- `UI.00-launch-unsigned` · **MOBILE_PASS** — Included in BrowserStack build 235b7b7b50635425bd819d81174ff35944173857
- `API.health` · **API_SPINE** — GET /healthz → 200
- `API.hr.login` · **BLOCKED** — Set MOBILE_E2E_HR_EMAIL + MOBILE_E2E_HR_PASSWORD to run HR API spine
- `API.employee.session` · **BLOCKED** — Set MOBILE_E2E_EMPLOYEE_BEARER (from activate) for employee API spine
