# Mobile E2E release gate — 20260816T235130Z

**Suite:** `smoke`
**Evidence:** `ops/evidence/mobile-e2e-gate-20260816T235130Z`

## Rule

**API PASS ≠ MOBILE PASS.** MOBILE_PASS only when Maestro opened the app on a real simulator/device.

## Counts

| Verdict | Count |
| --- | ---: |
| API_SPINE | 6 |
| BLOCKED | 5 |

## SHIP / NO-SHIP

| Product | Verdict |
| --- | --- |
| HR (unified `/hr`) | **NO-SHIP** |
| Employee | **NO-SHIP** |

Reason: Missing MOBILE_PASS for: real UI execution, unsigned entry, HR login/tabs, Employee activation credentials

## Host blockers

- `no_executable_ui_target`

## Matrix

- `UI.00-unsigned-entry` · **BLOCKED** — No simulator/device UI runtime ready: no_executable_ui_target
- `UI.05-method-switch-en` · **BLOCKED** — No simulator/device UI runtime ready: no_executable_ui_target
- `UI.01-hr-login` · **BLOCKED** — No simulator/device UI runtime ready: no_executable_ui_target
- `UI.02-hr-tabs` · **BLOCKED** — No simulator/device UI runtime ready: no_executable_ui_target
- `API.health` · **API_SPINE** — GET /healthz → 200
- `API.hr.login` · **API_SPINE** — HR login OK company=WATHEFNI
- `API.hr.me` · **API_SPINE** — GET /dashboard/mobile/me → 200
- `API.hr.priorities` · **API_SPINE** — GET /dashboard/mobile/priorities → 200
- `API.hr.leave.requested` · **API_SPINE** — GET /dashboard/mobile/leave?status=requested&limit=5 → 200
- `API.hr.assistant.capabilities` · **API_SPINE** — GET /dashboard/mobile/assistant/capabilities → 200
- `API.employee.session` · **BLOCKED** — Set MOBILE_E2E_EMPLOYEE_BEARER (from activate) for employee API spine
