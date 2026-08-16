# R5F permission matrix

| Actor | Read workspace | Plan admin | Eligibility | Enroll / confirm | Sensitive contrib / member | Employee self |
|---|---|---|---|---|---|---|
| Owner / HR with `benefits.manage` | yes | yes | yes | yes | yes | n/a |
| HR `benefits.read` only | yes | no | no | no | no | n/a |
| HR `benefits.enroll` | yes (with read) | no | no | yes | no | n/a |
| HR `benefits.sensitive` | yes (with read) | no | no | no | yes | n/a |
| HR without Benefits permission | 403 | 403 | 403 | 403 | 403 | n/a |
| Manager (default) | 403 | 403 | 403 | 403 | 403 | n/a |
| Employee `benefits` feature | n/a | no | no | elect/waive self only | permitted contribution display | self only |
| Unauthenticated | 401/403 | 401/403 | 401/403 | 401/403 | 401/403 | 401/403/503 |
