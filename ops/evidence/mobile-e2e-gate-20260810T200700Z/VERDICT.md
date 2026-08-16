# Mobile E2E release gate — 20260810T200700Z

**Suite:** `smoke`
**Evidence:** `ops/evidence/mobile-e2e-gate-20260810T200700Z`

## Rule

**API PASS ≠ MOBILE PASS.** MOBILE_PASS only when Maestro opened the app on a real simulator/device.

## Counts

| Verdict | Count |
| --- | ---: |
| BLOCKED | 4 |
| FAIL | 1 |

## SHIP / NO-SHIP

| Product | Verdict |
| --- | --- |
| HR (unified `/hr`) | **NO-SHIP** |
| Employee | **NO-SHIP** |

Reason: MOBILE_PASS=0 (no real UI execution succeeded)

## Host blockers

- `ios_simulator_runtime_missing`
- `adb_missing`
- `disk_free_lt_9gb_for_ios_runtime`
- `no_executable_ui_target`

## Matrix

- `UI.00-unsigned-entry` · **BLOCKED** — No simulator/device UI runtime ready: ios_simulator_runtime_missing, adb_missing, disk_free_lt_9gb_for_ios_runtime, no_executable_ui_target
- `UI.05-method-switch-en` · **BLOCKED** — No simulator/device UI runtime ready: ios_simulator_runtime_missing, adb_missing, disk_free_lt_9gb_for_ios_runtime, no_executable_ui_target
- `API.health` · **FAIL** — GET /health → 404
- `API.hr.login` · **BLOCKED** — Set MOBILE_E2E_HR_EMAIL + MOBILE_E2E_HR_PASSWORD to run HR API spine
- `API.employee.session` · **BLOCKED** — Set MOBILE_E2E_EMPLOYEE_BEARER (from activate) for employee API spine
