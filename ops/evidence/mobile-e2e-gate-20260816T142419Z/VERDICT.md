# Mobile E2E release gate — 20260816T142419Z

**Suite:** `smoke`
**Evidence:** `ops/evidence/mobile-e2e-gate-20260816T142419Z`

## Rule

**API PASS ≠ MOBILE PASS.** MOBILE_PASS only when Maestro opened the app on a real simulator/device.

## Counts

| Verdict | Count |
| --- | ---: |
| API_SPINE | 6 |
| BLOCKED | 1 |
| MOBILE_PASS | 4 |

## SHIP / NO-SHIP

| Product | Verdict |
| --- | --- |
| HR (unified `/hr`) | **SHIP** |
| Employee | **NO-SHIP** |

Reason: Missing MOBILE_PASS for: Employee activation credentials

## Host blockers

- `(none)`

## Matrix

- `UI.00-unsigned-entry` · **MOBILE_PASS** — Maestro flow passed on real UI runtime
- `UI.05-method-switch-en` · **MOBILE_PASS** — Maestro flow passed on real UI runtime
- `UI.01-hr-login` · **MOBILE_PASS** — Maestro flow passed on real UI runtime
- `UI.02-hr-tabs` · **MOBILE_PASS** — Maestro flow passed on real UI runtime
- `API.health` · **API_SPINE** — GET /healthz → 200
- `API.hr.login` · **API_SPINE** — HR login OK company=WATHEFNI
- `API.hr.me` · **API_SPINE** — GET /dashboard/mobile/me → 200
- `API.hr.priorities` · **API_SPINE** — GET /dashboard/mobile/priorities → 200
- `API.hr.leave.requested` · **API_SPINE** — GET /dashboard/mobile/leave?status=requested&limit=5 → 200
- `API.hr.assistant.capabilities` · **API_SPINE** — GET /dashboard/mobile/assistant/capabilities → 200
- `API.employee.session` · **BLOCKED** — Set MOBILE_E2E_EMPLOYEE_BEARER (from activate) for employee API spine
