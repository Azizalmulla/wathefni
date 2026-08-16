# R5J security negatives

| Negative | Result |
|---|---|
| Unauthenticated workspace | 401/403/503 |
| HR without `workforce_planning.*` | 403; not empty-plans / not “No workforce gap” / not “0 planned hires” |
| Manager administration workspace | 403 |
| Empty manager org scope | Zero demand; not company-wide |
| Export without `workforce_planning.export` | 403 |
| Planner-only approve | 403 |
| Cost without `workforce_planning.cost` | Forbidden / redacted |
| Handoff without `workforce_planning.execute` | 403 |
| Non-KWD create | 422 `currency_unsupported_no_fx` |
| Foreign tenant plan | 403/404 |
| Employee App namespace | Not registered |
| HR Mobile namespace | Not registered |
| Assistant create/approve/handoff/forecast | `mutation_forbidden` |
| Enable without JA | `ja_must_be_enabled` / JA hard blocks enable |
| JA off after history | Workspace unavailable; no guessed titles |
| Recruiting handoff retry | Idempotent; no duplicate requisition |
