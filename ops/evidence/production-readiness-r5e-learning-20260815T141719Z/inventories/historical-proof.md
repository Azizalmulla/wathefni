# R5E historical reconstruction

| Record | Proof |
|---|---|
| Catalog / program version | C2 `ld_item_versions` + assignment `item_version` pin |
| Assignment + source | `source` / `actor_phone` / `required` / `due_date` retained after later disable |
| Approval | Request row keeps `status`, `decided_by_phone`, `assignment_id` separately from enrollment |
| Enrollment | Approved-request assignment `source=employee_requested`; session enroll has `offering_id` |
| Session attendance | Metadata only; does not rewrite completion |
| Completion evidence | `evidence_source` / `evidence_ref` on `ld_completions` |
| Certificate + expiry / renewal | Original + renewed rows; `renewal_of` link; expiry derived |
| Development fulfillment | Link row with `silently_closed_c3=false`; C3 status unread-mutated |
| Later policy | `later_policy_does_not_rewrite_history=true`; mandatory replay does not duplicate |

Later catalog / policy / job changes do not rewrite these historical rows.
