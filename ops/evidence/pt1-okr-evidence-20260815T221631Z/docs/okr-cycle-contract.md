# OKR cycle contract

- Table: `perf_okr_cycles`
- Statuses: `draft` → `active` → `closed`
- Fields: bilingual name, period start/end, scope, org unit, visibility policy, version / row_version, closed_at
- Scoring snapshot: `inherits_alignment_score=false`
- Constraint: `metadata.review_cycle_id` must be null
- Honesty: `okr_cycle_is_not_review_cycle = true`
- Membership: `perf_okr_cycle_objectives` join — does not ALTER `perf_objectives`
- Distinct from C2 `perf_review_cycles` (proved: OKR cycle id absent from review table)
