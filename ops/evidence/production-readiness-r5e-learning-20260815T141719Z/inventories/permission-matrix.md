# R5E permission matrix

| Permission | Owner / HR admin | Manager | Viewer | Employee self |
|---|---|---|---|---|
| `learning.read` | Yes | Yes (scoped) | Yes | via employee feature `view` |
| `learning.manage` | Yes | No | No | No |
| `learning.assign` | Yes | Yes (scoped) | No | No |
| `learning.approve` | Yes | Yes (scoped) | No | No |
| Catalog author | manage | No | No | No |
| Completion / evidence verifier | manage | No | No | Only if self-attestation explicitly allowed |
| Certification administration | manage | No | No | No |
| Request learning | — | — | — | feature action `request` |

Manager scope comes from `context_manager_employee_keys` (canonical org). Empty scope → empty lists, `company_wide=false`.

Employee cannot list another employee's learning history. Cross-tenant assignment reads return no foreign rows.
