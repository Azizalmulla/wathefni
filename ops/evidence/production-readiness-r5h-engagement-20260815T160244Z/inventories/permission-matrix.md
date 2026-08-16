# R5H permission matrix

| Actor | Admin workspace | Launch / manage surveys | Results / segments | Export | Manager aggregates | Employee participate | Resolve anonymous answers |
|---|---|---|---|---|---|---|---|
| Owner / HR with full `engagement.*` | yes | yes | yes (threshold-gated) | if `engagement.export` | n/a (admin path) | n/a | denied (anonymous fail-closed) |
| HR `engagement.read` only | yes (read) | no | yes (threshold-gated) | 403 | n/a | n/a | denied |
| Manager (`engagement.manager` only) | 403 | 403 | no admin results | 403 | yes, own scope only; empty ≠ company-wide | n/a | 403 |
| Viewer | 403 | 403 | 403 | 403 | 403 | n/a | 403 |
| Employee (entitled) | n/a | n/a | no | n/a | n/a | own invitations only | n/a |
| Other employee | n/a | n/a | n/a | n/a | n/a | 403/404 `not_in_audience` | n/a |
| Unauthenticated | 401/403/503 | 401/403/503 | 401/403/503 | 401/403/503 | 401/403/503 | 401/403/503 | 401/403/503 |
| Foreign tenant | 403/404 | 403/404 | 403/404 | 403/404 | 403/404 | 403/404 | 403/404 |
