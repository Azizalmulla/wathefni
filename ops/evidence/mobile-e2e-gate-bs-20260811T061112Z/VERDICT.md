# Mobile E2E release gate — 20260811T061112Z

**Suite:** `bs-smoke`
**Evidence:** `ops/evidence/mobile-e2e-gate-bs-20260811T061112Z`

## Rule

**API PASS ≠ MOBILE PASS.** MOBILE_PASS only when Maestro opened the app on a real simulator/device.

## Counts

| Verdict | Count |
| --- | ---: |
| API_SPINE | 6 |
| BLOCKED | 1 |
| FAIL | 2 |

## SHIP / NO-SHIP

| Product | Verdict |
| --- | --- |
| HR (unified `/hr`) | **NO-SHIP** |
| Employee | **NO-SHIP** |

Reason: MOBILE_PASS=0 (no real UI execution succeeded)

## Host blockers

- `java_runtime_missing_for_maestro`
- `ios_simulator_runtime_missing`
- `adb_missing`
- `disk_free_lt_9gb_for_ios_runtime`
- `no_executable_ui_target`

## Matrix

- `UI.browserstack.sessions` · **FAIL** — passed=0 failed=1 error=0 status=failed
- `API.health` · **API_SPINE** — GET /healthz → 200
- `API.hr.login` · **API_SPINE** — HR login OK company=WATHEFNI
- `API.hr.me` · **API_SPINE** — GET /dashboard/mobile/me → 200
- `API.hr.priorities` · **API_SPINE** — GET /dashboard/mobile/priorities → 200
- `API.hr.leave.requested` · **API_SPINE** — GET /dashboard/mobile/leave?status=requested&limit=5 → 200
- `API.hr.assistant.capabilities` · **API_SPINE** — GET /dashboard/mobile/assistant/capabilities → 200
- `API.employee.session` · **BLOCKED** — Set MOBILE_E2E_EMPLOYEE_BEARER (from activate) for employee API spine
- `API.leave.reconcile` · **FAIL** — {"approve": "requested", "reject_reason_persisted": false, "reject": "requested"}
