# R5F authority mapping

| Concern | Authority |
|---|---|
| Plan / version / eligibility / enrollment / waiver / coverage / contribution / handoff / member ref | Frozen Wave 6 C3 `benefits_administration_c3` |
| HTTP / HR Web / Employee App | Thin adapters (`benefits_http`, `benefits_surfaces`, dashboard + employee clients) |
| Dependent master | Wave 3 `employee_dependents` only |
| Payroll execution / deduction / payment | Payroll (optional). Benefits may emit an explicit handoff only |
| Claims / adjudication | Out of scope |
| Kuwait statutory formulas | Not invented; configured policy only |
| Company / employee identity | Authenticated server context only |
