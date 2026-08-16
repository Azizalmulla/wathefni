# R5E API inventory

Dashboard prefixes: `/dashboard/learning`, `/dashboard/posthire/learning`

| Method | Path | Authority |
|---|---|---|
| GET | `/workspace` | `learning.read` |
| GET/POST | `/catalog` | read / `learning.manage` |
| GET | `/programs` | `learning.read` |
| POST | `/programs/children` | `learning.manage` |
| GET/POST | `/assignments` | read / `learning.assign` or manage |
| POST | `/assignments/{assignment_id}/advance` | assign or manage (cannot mark completed) |
| GET/POST | `/requests` | read / assign, manage, or approve |
| POST | `/requests/{request_id}/decide` | `learning.approve` or manage |
| GET/POST | `/sessions` | read / manage |
| POST | `/sessions/{offering_id}/enroll` | assign or manage; capacity server-side |
| POST | `/sessions/{offering_id}/attendance` | manage (metadata only) |
| GET/POST | `/completions` | read / manage (evidence-backed) |
| GET/POST | `/certificates` | read / manage |
| GET/POST | `/mandatory` | read / manage |
| POST | `/mandatory/{policy_id}/generate` | manage (idempotent) |
| GET/POST | `/development-links` | read / manage (does not close C3) |
| GET | `/history` | `learning.read` |
| GET | `/team` | scoped manager view |

Employee App (self only):

| Method | Path |
|---|---|
| GET | `/app/learning` |
| GET | `/app/learning/catalog` |
| GET | `/app/learning/assignments` |
| GET | `/app/learning/sessions/{offering_id}` |
| POST | `/app/learning/requests` |
| GET | `/app/learning/certificates` |
| POST | `/app/learning/completions` (guarded; mandatory self-complete forbidden by default) |

Company and actor identity come from authenticated context. No `X-Company-Code` write authority.
