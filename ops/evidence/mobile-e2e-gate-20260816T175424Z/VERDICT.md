# Mobile E2E release gate — 20260816T175424Z

**Suite:** `smoke`
**Evidence:** `ops/evidence/mobile-e2e-gate-20260816T175424Z`

## Rule

**API PASS ≠ MOBILE PASS.** MOBILE_PASS only when Maestro opened the app on a real simulator/device.

## Counts

| Verdict | Count |
| --- | ---: |
| API_SPINE | 6 |
| BLOCKED | 1 |
| MOBILE_PASS | 1 |

## SHIP / NO-SHIP

| Product | Verdict |
| --- | --- |
| HR (unified `/hr`) | **NO-SHIP** |
| Employee | **NO-SHIP** |

Reason: Missing MOBILE_PASS for: unsigned entry, Arabic/RTL critical path, HR login/tabs, Employee activation credentials

## Host blockers

- `(none)`

## Matrix

- `UI.hr-session-ar` · **MOBILE_PASS** — Maestro flow passed on real UI runtime (android:emulator-5554)
- `API.health` · **API_SPINE** — GET /healthz → 200
- `API.hr.login` · **API_SPINE** — HR login OK company=WATHEFNI
- `API.hr.me` · **API_SPINE** — GET /dashboard/mobile/me → 200
- `API.hr.priorities` · **API_SPINE** — GET /dashboard/mobile/priorities → 200
- `API.hr.leave.requested` · **API_SPINE** — GET /dashboard/mobile/leave?status=requested&limit=5 → 200
- `API.hr.assistant.capabilities` · **API_SPINE** — GET /dashboard/mobile/assistant/capabilities → 200
- `API.employee.session` · **BLOCKED** — Set MOBILE_E2E_EMPLOYEE_BEARER (from activate) for employee API spine
