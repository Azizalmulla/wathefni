# R5D API inventory

Company and actor identity come from authenticated `dashboard_context` only. No `X-Company-Code` write authority. JA Job Profile ≠ Recruiting Job ≠ Requisition.

Namespace: `/dashboard/job-architecture`

| Method | Path | Authority |
|---|---|---|
| GET | `/workspace` | summary; disabled → `resource_state=unavailable`, `counts=null` |
| GET | `/catalog` | families, functions, profiles, grades, levels, career edges |
| GET / POST | `/families` | list / upsert family (`job_architecture.manage`; publish needs `.publish` or `.manage`) |
| GET / POST | `/functions` | list / upsert function |
| GET / POST | `/profiles` | list / upsert JA job profile |
| GET / POST | `/grades` | list / upsert canonical grade |
| GET / POST | `/levels` | list / upsert canonical level |
| GET / POST | `/career-edges` | list / create promotion, lateral, specialist, manager edges |
| GET / POST | `/assignments` | list / assign employment architecture (mapping perm on write) |
| POST | `/positions` | link org position to a profile (mapping) |
| GET | `/mappings` | legacy title/grade queue |
| POST | `/mappings/migrate` | deterministic unique auto-map only |
| POST | `/mappings/{mapping_id}/resolve` | authorized human resolve |
| GET | `/history` | version / audit events |
| GET / POST | `/refs` | optional Talent / Recruiting refs |
| DELETE | `/{entity_type}` | always `403 destructive_delete_forbidden` |

No `/app/job-architecture` product routes. Employee App and HR Mobile are not R5D surfaces.
