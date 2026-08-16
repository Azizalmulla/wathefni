# Payroll Authority P1 — Qualification

**Verdict: PASS**  
**Stamp:** `20260807T214004Z`  
**Checks:** 57 PASS / 0 FAIL

## Sealed snapshot schema

- `payroll_authority_snapshots` (+ `payroll_authority_snapshot_lines`, `payroll_authority_snapshot_events`)
- `payroll_component_catalog` (Kuwait-ready identity hooks; no statutory formulas)
- `money_authority ∈ {wathefni, external}`
- status ∈ {sealed, replaced, revoked}
- Unique current sealed per `(company_code, employee_key, period_start, period_end)`

## Authority transitions

| Transition | Result |
|---|---|
| Mode B import → seal | `money_authority=external` sealed |
| Repeat seal | idempotent |
| Silent mutate | refused |
| Stale second import seal | refused (use replace) |
| Replace | prior `replaced`, new `sealed` |
| Mode A native preview seal | REFUSED |
| Wave 4 period close | not money authority |
| Official PDF | requires sealed external + linked payslip |

## Evidence

`/opt/wathefni/ops/evidence/payroll-authority-p1-regression-p2-20260807T214004Z`

## Remaining blockers for P2

1. Attendance/leave input assembly into sealed Mode A path  
2. Mode A authoritative-finalize still locked  
3. SYNTHETIC_ONLY  
4. Counsel-gated statutory rates  
5. payment_processing disabled  

**Do not start P2 / Employee App P1 / Setup Console / Auth Wave 2 Phase 6 automatically.**
