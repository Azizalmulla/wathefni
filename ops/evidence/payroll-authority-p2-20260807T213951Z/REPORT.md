# Payroll Authority P2 — Qualification

**Verdict: PASS**  
**Stamp:** `20260807T213951Z`  
**Checks:** 43 PASS / 0 FAIL

## Payroll input snapshot schema

- `payroll_input_snapshots` (+ employees, lines, issues, events)
- status ∈ {assembling, needs_review, ready, locked, superseded}
- `attendance_payroll_mode` ∈ {required, informational, ignored}
- P1 bridge: `payroll_authority_snapshots.input_snapshot_id` (nullable)

## Overlap / precedence

- Only approved leave affects payroll
- Pending/rejected/cancelled excluded
- Approved unpaid leave suppresses attendance absence (no double count)
- Paid leave not treated as unpaid absence
- OT / rest-day / PH work = distinct facts, **no money**
- Overnight shifts anchored to shift work_date; timezone Asia/Kuwait

## Readiness / locking

- Unresolved required attendance → `needs_review` / lock fail-closed
- Informational mode does not block lock
- Locked inputs immutable; source changes require supersede + new version
- Repeated assemble with unchanged sources is idempotent

## Evidence

`/opt/wathefni/ops/evidence/payroll-authority-p2-20260807T213951Z`

## Blockers for P3

1. Time-pay / component rules  
2. OT/sick/PH statutory money (counsel)  
3. Mode A finalize still locked  
4. SYNTHETIC_ONLY  
5. payment_processing disabled  

**Do not start P3 / Employee App P1 / Setup Console / Auth Wave 2 Phase 6 automatically.**
