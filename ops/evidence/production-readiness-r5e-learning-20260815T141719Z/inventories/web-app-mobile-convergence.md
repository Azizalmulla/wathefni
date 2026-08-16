# R5E Web / App convergence

| Fact | HR Web | Employee App | HR Mobile |
|---|---|---|---|
| Assignment list | `/dashboard/learning/assignments` | `/app/learning` + `/app/learning/assignments` (self) | Not shipped |
| Catalog | workspace Catalog tab | `/learning/catalog` | Not shipped |
| Certificates / expiry | Certifications tab | `/learning/certificates` | Not shipped |
| Session | Sessions tab | `/learning/session?session_id=` | Not shipped |
| Request / approve | Requests tab (HR/manager) | POST `/app/learning/requests` | Not shipped |

Journey A proved the same `assignment_id` is visible to HR list and employee workspace. Status is server-decorated (`enrolled` / `attended` / `completed`); clients do not own it.

HR Mobile Learning admin is intentionally absent.
