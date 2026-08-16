# R5G E2E journeys A–G

Proved on staging tenant `R5G7A4629` (`R5G_EMPLOYEE_RELATIONS_SURFACE_DB_PASS`, 87/0).

| Journey | Result |
|---|---|
| A Case lifecycle | Authorized intake → triage → assign investigator → investigate → evidence → finding → outcome → closure; history reconstructable; intake is not a finding; investigation is not a finding/outcome |
| B Need-to-know | HR without `er.*` cannot list/read. INV_A lists/reads Case A only. INV_A IDOR on Case B blocked. Ordinary HR empty assignment is empty, not company-wide. View-only grant sees header; investigator notes hidden |
| C Evidence | Authorized investigator retrieves permitted evidence; raw URL stripped / sealed. Unauthorized ER participant 403; raw URL hidden |
| D Manager | Manager of involved employee has zero cases and cannot read the case. Contribution without grant denied. Explicit scoped contribution allowed and is not full case access |
| E Employment handoff | Governed outcome does not mutate employment. Explicit handoff created, `applied=false`, idempotent replay of the same case+outcome |
| F Mobile | Authorized ER actor receives privacy-safe queue/summary (generic copy; no notes). Unauthorized mobile principal fails closed |
| G Module off | Historical case retained. New intake blocked. Workspace `unavailable` with `counts=None`. Notifications suppressed after commit |

Also proved: Performance/Talent/Payroll/Benefits/Engagement OFF composition; tenant isolation; export requires `er.export`; Assistant unauthorized/mutation-forbidden/metadata-only; Wave 5 forbids allegation text and allows typed fact; EN + AR status labels; 403 is not empty-cases.
