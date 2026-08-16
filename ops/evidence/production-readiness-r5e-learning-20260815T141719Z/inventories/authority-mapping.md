# R5E authority mapping

| Product object | Canonical owner | Surface may |
|---|---|---|
| Catalog item / program / version | Wave 6 C2 `ld_learning_items` / `ld_item_versions` / `ld_program_items` | Author via C2 upsert |
| Assignment | C2 `ld_assignments` | Create / list / decorate; cannot fabricate completion |
| Enrollment | Assignment with `offering_id` and/or approved-request assignment | Capacity-checked enroll |
| Attendance | Assignment `metadata.attended` | Record without calling `record_completion` |
| Completion | C2 `ld_completions` | Evidence-backed `record_completion_guarded` |
| Certification | C2 `ld_certifications` | Issue / renew; expiry derived |
| Request / approval | C2 `ld_learning_requests` | Surfaces require reject reason |
| Mandatory policy / generation | C2 `ld_mandatory_policies` + `obligation_key` | Idempotent replay |
| Development fulfillment | C2 `ld_development_fulfillment_links` | Attach evidence; `silently_closed_c3=false` |
| Development action status | Wave 4 C3 | Read only |
| Skills / competency verification | Canonical competency / Talent authority | Learning completion is evidence only |
| Job / grade hierarchy | Wave 6 C1 | Optional reference only |
| Talent HiPo / potential / readiness | Wave 4 C5/C6 | Never written by Learning |

No second Learning model. No client-side canonical state.
