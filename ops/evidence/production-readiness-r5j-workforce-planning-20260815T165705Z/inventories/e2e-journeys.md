# R5J E2E journeys A–I

Proved on staging tenant `R5J9C6EE6` (`R5J_WORKFORCE_PLANNING_SURFACE_DB_PASS`, 94/0).

| Journey | Result |
|---|---|
| A Baseline | JA-assigned actual workforce (2) → freeze baseline from canonical actual → later assign E3 → baseline remains 2 / immutable. Baseline is not a second actual SoT |
| B Scenario | Same baseline → Base + Growth scenarios with different demand → Growth does not mutate Base (or actual). Actual still 3 |
| C Projection | Versioned assumptions + explicit new/replacement/reduction demand → planned HC = 4 (`2 + 3 − 1`) → same inputs reproduce. Wave 5 turnover is not a silent forecast. No AI black box |
| D Cost | Scenario planned cost labeled planned/estimated, currency KWD, not payroll. USD create 422 `currency_unsupported_no_fx` |
| E Approval | Submit → approve → actual still 3. Approved scenario immutable. Approval ≠ actual workforce change |
| F Recruiting OFF | Approved demand handoff is `approved_unexecuted` / externally executable. No employment mutate. No auto-post/hire. Retry idempotent |
| G Recruiting ON | Explicit handoff → exactly one linked DRAFT requisition. No job posted. No hire. Retry does not duplicate |
| H Actual vs plan | After later actual change: actual 3 vs planned 4. Uses canonical actual, not frozen baseline 2, not a copied WFP SoT |
| I Optional dependencies | Full planning works with Compensation OFF + Talent OFF + Payroll OFF + Performance OFF + Recruiting OFF at start |

Also proved: JA hard-blocks enable; JA off → WFP unavailable (no guessed plans); disable hides workspace (`counts=None`), preserves history/handoffs, does not delete requisitions, suppresses new notifications; HTTP unauthenticated not public; HR without `workforce_planning.*` 403 is not empty-plans / not “0 planned hires” / not “No workforce gap”; manager admin 403; empty manager scope zero demand; export without `.export` is 403; planner-only cannot approve; tenant isolation; Assistant mutations forbidden.
