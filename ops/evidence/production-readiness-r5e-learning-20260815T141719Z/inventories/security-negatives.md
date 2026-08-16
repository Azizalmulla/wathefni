# R5E security negatives

Proved via HTTP TestClient on staging after journeys A–F.

| Negative | Result |
|---|---|
| Unauthenticated dashboard | 401 or 403 |
| Unauthenticated employee | 401, 403, or 503 |
| Cross-tenant assignment list | 200 with no foreign employee rows |
| Manager empty org scope | `total=0` |
| Manager catalog author | 403 |
| HR read-only catalog write | 403 |
| Employee IDOR | Self key only; cannot enumerate another employee's assignments |
| Employee mandatory / arbitrary complete | 403 / 404 / 422 |
| Live Learning routes | Not `capability_not_released`; not public |
| Live Benefits / Comp Planning / WFP | Still `capability_not_released` |

R2 staging DB **69/0**. Internal-auth **ALL CHECKS PASSED**.
