# R5D security negatives

| Case | Result |
|---|---|
| Unauthenticated GET `/workspace` | 401/403 |
| Tenant B lists families | 200 with no tenant A codes |
| Manager with read only POSTs family | 403 |
| HR without manage POSTs grade | 403 |
| HR without mapping POSTs migrate | 403 |
| DELETE `/profiles` | 403 `destructive_delete_forbidden` |
| Client `X-Company-Code` | not accepted as write authority |
| Empty allowlist after R5D | admits when `customer_enableable`; kill switch still wins |
| Learning / Comp / WFP namespaces | still `capability_not_released` |
