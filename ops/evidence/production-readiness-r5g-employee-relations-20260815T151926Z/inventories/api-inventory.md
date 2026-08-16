# R5G API inventory

Namespaces (no `/app/employee-relations`):

- `DASH_PREFIXES = ("/dashboard/employee-relations", "/dashboard/posthire/employee-relations")`
- `MOBILE_PREFIX = "/dashboard/mobile/employee-relations"`

Dashboard / posthire (each path bound on both prefixes):

- `GET ""` / `GET /workspace` — workspace summary
- `GET /cases` — grant-scoped case list
- `GET /my-work` — actions assigned to the authenticated ER actor
- `GET /case-types` — case types
- `POST /case-types` — upsert case type (`er.manage`)
- `POST /cases` — intake
- `GET /cases/{case_id}` — case detail (grant required)
- `POST /cases/{case_id}/triage`
- `POST /cases/{case_id}/assign`
- `POST /cases/{case_id}/grants`
- `POST /cases/{case_id}/notes`
- `POST /cases/{case_id}/evidence`
- `GET /evidence/{evidence_id}/content` — sealed retrieval
- `POST /cases/{case_id}/findings`
- `POST /cases/{case_id}/outcomes`
- `POST /cases/{case_id}/closure`
- `POST /cases/{case_id}/handoffs` — Wave 3 employment-change handoff
- `GET /cases/{case_id}/history`
- `POST /cases/{case_id}/contribution` — scoped manager/participant contribution
- `GET /export` — separately permissioned (`er.export`)
- `POST /assistant` — read/explain only

HR Mobile (authorized ER actors only):

- `GET /dashboard/mobile/employee-relations` — privacy-safe queue
- `GET /dashboard/mobile/employee-relations/cases/{case_id}` — scoped summary
- `POST /dashboard/mobile/employee-relations/cases/{case_id}/acknowledge`
