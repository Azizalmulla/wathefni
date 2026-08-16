# R5D historical reconstruction

- Profile rename keeps the same `profile_id` and increments `effective_version`.
- Legacy mapping `raw_value` is unchanged by rename, human resolve, or disable.
- Employment assignment continues to point at the stable profile id.
- `ja_audit_events` records upsert / resolve / enable / disable.
- Hard `DELETE` is refused (`destructive_delete_forbidden`); retire / supersede only.
