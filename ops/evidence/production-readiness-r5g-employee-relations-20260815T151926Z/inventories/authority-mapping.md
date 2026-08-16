# R5G authority mapping

| Concern | Authority |
|---|---|
| Case / intake / triage / investigation / evidence / finding / outcome / closure / grants / notes / history | Frozen Wave 6 C4 `employee_relations_c4` |
| HTTP / HR Web / HR Mobile | Thin adapters (`employee_relations_http`, `employee_relations_surfaces`, dashboard + HR Mobile clients) |
| Employment mutation / termination / suspension / transfer / payroll | Wave 3 employment lifecycle only. ER may emit an explicit handoff |
| Payroll execution | Payroll (optional). ER never mutates payroll truth |
| Company / actor identity | Authenticated server context only |
| Wave 5 intelligence | Explicitly safe typed facts only; no allegation/narrative/note/evidence free text |
| Assistant | Read/explain only; same grant + evidence checks; no mutations |
| ER scoring | Out of scope; forbidden |
