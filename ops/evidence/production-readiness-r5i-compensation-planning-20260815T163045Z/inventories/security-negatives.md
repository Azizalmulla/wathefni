# R5I security negatives

| Negative | Result |
|---|---|
| Unauthenticated workspace | 401/403/503 |
| HR without `comp_planning.*` | 403; not “No compensation changes” |
| Manager administration workspace | 403 |
| Empty manager org scope | `company_wide=false`, `rows=[]` |
| Export without `comp_planning.export` | 403 |
| Recommend-only approve | 403 |
| Same actor recommend+approve | C6 `sod_violation_recommend_approve_same_actor` |
| Non-KWD create | 422 `currency_unsupported_no_fx` |
| Foreign tenant cycle | 403/404 |
| Employee App namespace | Not registered |
| HR Mobile namespace | Not registered |
| Assistant `change_salary` | `mutation_forbidden` |
| HiPo auto-convert | `hipo_not_automatic_pay` |
| Enable without JA | `ja_must_be_enabled` |
