# R5A Capability Honesty — verification log

**Stamp:** `PRODUCTION_READINESS_R5A_CAPABILITY_HONESTY_FULL_PASS`
**Evidence:** `ops/evidence/production-readiness-r5a-capability-honesty-20260812T183621Z/`
**Qualify:** `ops/qualify-production-readiness-r5a-capability-honesty.sh`
**When:** 2026-08-12T18:36:21Z

## Local

| Check | Result |
|---|---|
| Dashboard named vitest | 4 files, 39 passed |
| Dashboard full vitest | 89 files, 481 passed, 0 failed |
| `smoke-test-r5a-capability-honesty.py` | 205 passed, 0 failed |

## Staging

| Check | Result |
|---|---|
| Copy + py_compile | STAGING_COPY_OK |
| `smoke-test-r5a-capability-honesty-db.py` | 30 passed, 0 failed |
| Live reserved namespaces | 26 passed, 0 failed; Intelligence namespace not stolen |

## Regressions (all rc=0)

| Suite | Result |
|---|---|
| Wave 6 product unit | 48 passed |
| Job Architecture C1 | 27 passed (unit-only) |
| Learning C2 | 35 passed (unit-only) |
| Benefits C3 | 36 passed (unit-only) |
| ER C4 | 33 passed (unit-only) |
| Engagement C5 | 33 passed (unit-only) |
| Comp Planning C6 | 39 passed (unit-only) |
| Workforce Planning C7 | 40 passed (unit-only) |
| Wave 5 product unit | 50 passed |
| Wave 4 product unit | 49 passed |
| Wave 3 product unit | 42 passed |
| Wave 2 product unit | 47 passed |
| Wave 1 product unit | 28 passed |
| R2 unit / staging DB | 84 / 69 |
| R3 unit / staging DB | 61 / 18 |
| R4 unit / staging DB | 40 / 9 |
| Interaction authority contracts | OK |
| Internal-auth staging | 10 passed, ALL CHECKS PASSED |

## Honesty probes

- Customer cannot enable Performance, Talent, or Wave 6 modules (409 contract + omitted Setup cards).
- Stored Performance overlay `enabled=true` and JA settings row preserved.
- Env allowlist still opens domain `runtime_gate_for_company` for internal qualification.
- `customer_usable` remains false even when stored enabled and runtime are true.
- Wave 5 Intelligence workspace still mounted; `/dashboard/posthire/intelligence` not fail-closed as an unreleased HCM module.
