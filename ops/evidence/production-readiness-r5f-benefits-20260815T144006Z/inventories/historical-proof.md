# R5F historical reconstruction

Proved on `R5FB7930E`:

- Enrollment and coverage pin `plan_version` at election/confirm time
- Later `upsert_plan` bumps current version; prior coverage row keeps original version
- `list_history` returns events, enrollments, coverage, plan versions
- `later_policy_does_not_rewrite_history=true`
- Module disable retains coverage/elections
