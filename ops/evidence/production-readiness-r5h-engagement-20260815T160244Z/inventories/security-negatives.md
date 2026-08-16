# R5H security negatives

| Negative | Result |
|---|---|
| Unauthenticated `/dashboard/engagement/workspace` | 401/403/503 |
| Unauthenticated `/app/engagement` | 401/403/503 |
| HR without `engagement.*` | 403; body is not “No surveys” |
| Manager admin workspace | 403 |
| Manager empty org scope `/manager` | 200, `company_wide=false`, suppressed/empty |
| Admin resolve anonymous answers | 403 `anonymous_respondent_answer_map_unavailable` |
| Export without `engagement.export` | 403 |
| Foreign tenant campaign id | 403/404 |
| Employee not in audience | 403/404/422 `not_in_audience` |
| Employee workspace analytics | `company_analytics_included=false`; no scores |
| `X-Company-Code` write authority | Not accepted |
| `/dashboard/mobile/engagement` | Not registered |
| Comp Planning / WFP namespaces | Still `capability_not_released` |
