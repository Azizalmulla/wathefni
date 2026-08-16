# R5I authority mapping

| Product action | Canonical owner | Surface role |
|---|---|---|
| Cycle / eligibility freeze | `compensation_planning_c6` | HTTP/HR Web adapter |
| Budget math / over-budget | C6 | Backend only |
| JA grade / level / profile | `job_architecture_c1` | Hard dependency; Comp references only |
| Salary band / range | C6 (`cp_salary_bands`) | Comp policy, not JA |
| Recommendation / calibration / approval / finalize | C6 | HTTP derives actor from context |
| Change package | C6 `cp_apply_handoffs` | Surface adds idempotent replay |
| Employee salary / employment terms | Employment C1 | Comp must not mutate |
| Payroll execution / paid | Payroll | Explicit handoff only |
| Performance rating | Performance | Optional advisory context |
| HiPo / potential | Talent | Optional advisory context; never auto-pay |
