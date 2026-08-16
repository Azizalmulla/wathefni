# R5F E2E journeys A–F

Proved on staging tenant `R5FB7930E` (`R5F_BENEFITS_SURFACE_DB_PASS`, 75/0).

| Journey | Result |
|---|---|
| A Eligibility + enrollment | HR versioned plan + open rule → evaluate eligible → start → employee elects → status `elected` not `coverage_active` → HR `confirm_enrollment` creates coverage; `provider_confirmed=false` |
| B Waiver | EMP2 eligible → waive → waiver preserved → later evaluation still eligible and not enrolled; waiver ≠ ineligibility |
| C Dependents | Canonical `employee_dependents` row exists and is not covered → `link_dependent_coverage` references that id → covered via relationship; no second dependent master |
| D Payroll OFF | Contribution defined (`paid_amount=None`) → handoff returns `payroll_handoff_disabled`; journey does not fail |
| E Payroll ON | Enable handoff + payroll module → handoff created → `applied_to_payroll=false`; Payroll remains authority; finalized payroll not rewritten |
| F History | Plan version bump → prior coverage retains original `plan_version`; later policy does not rewrite history |

Also proved: Learning/Talent/JA/Payroll OFF composition; module-off history + notification suppression after commit; tenant isolation; manager 403; HR without permission 403; employee IDOR; employee cannot confirm coverage.
