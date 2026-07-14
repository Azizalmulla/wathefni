# HR-1 — Mobile API Compatibility Matrix

For each planned Wathefni HR V1 feature, whether the current dashboard HTTP surface is reusable.

Legend:

- **reuse** — already safe for mobile with operator-mobile auth context
- **adapt** — safe after small response/validation adjustment (dedicated mobile adapter optional)
- **dedicated** — unsuitable as-is; needs a dedicated `/dashboard/mobile/...` endpoint
- **unavailable** — no safe endpoint yet; capability must stay disabled

Mutations must continue through existing authoritative registries and audit paths. Do not duplicate business logic.

## HR V1

| Feature | Dashboard surface today | Status | Notes |
| --- | --- | --- | --- |
| `hr_tasks` | post-hire task / delivery summaries | adapt | Needs compact mobile DTO; auth + scope already backend-current |
| `leave_approvals` | `/dashboard/posthire/leave*` decide actions | adapt | Reuse decide registry; slim list/detail payloads for mobile |
| `onboarding_review` | `/dashboard/posthire/onboarding*` | adapt | Same |
| `document_review` | onboarding/compliance document routes | adapt | Keep audit; mobile-friendly file metadata |
| `attendance_exceptions` | `/dashboard/posthire/attendance` | adapt | HR-0 status filter already fixed |
| `today_shifts` | shifts dashboard reads | adapt | Day-scoped query preferred |
| `shift_swap_decisions` | shift swap decide paths | adapt | Confirmation UX on client |
| `employee_search` | `/dashboard/posthire/employees` | adapt | Requires `employees.read` grant; manager scope enforced |
| `employee_quick_profile` | employee profile routes | adapt | Strip browser-only chrome fields |
| `delivery_alerts` | delivery / outbound status reads | dedicated | Browser pages are heavy; need mobile alert feed |

## Recruiting V1

| Feature | Dashboard surface today | Status | Notes |
| --- | --- | --- | --- |
| `candidate_rankings` | prehire ranking/summary | adapt | Mark advisory in UI; no auto-act |
| `candidate_summary` | candidate detail | adapt | |
| `candidate_evidence` | evidence / concerns panels | adapt | Must remain visible |
| `candidate_cv` | CV view/preview/download | reuse | HR-0 audit required |
| `candidate_shortlist` | candidate.manage actions | adapt | Registry + audit |
| `candidate_reject` | candidate.decide | adapt | Explicit confirmation required |
| `candidate_hire` | candidate.decide | adapt | Explicit confirmation required |
| `interview_status` | interview reads | adapt | |
| `interview_notes` | interview notes write | adapt | |
| `candidate_communication_status` | messaging status | adapt | Read-only mobile V1 |
| `new_candidate_push` | — | unavailable | No safe mobile push contract |
| `interview_reschedule` | partial browser | unavailable | Until dedicated safe endpoint |
| `kanban_stage_management` | browser kanban | unavailable | No free-form stage mutation |
| `bulk_import` | import batches | unavailable | |
| `job_pipeline_configuration` | settings | unavailable | |
| `ai_scoring_configuration` | settings | unavailable | |

## Auth / bootstrap

| Feature | Status | Notes |
| --- | --- | --- |
| Operator login/refresh/logout | **dedicated** (shipped HR-1) | `/dashboard/mobile/auth/*` |
| Capability bootstrap | **dedicated** (shipped HR-1) | `GET /dashboard/mobile/me` |
| Browser dashboard login | unchanged | `/dashboard/auth/*` |
| Employee App auth | unchanged | `/app/auth/*` |

## Cross-tenant / authority

All reused or adapted endpoints must authenticate via operator-mobile context (or equivalent backend-current dashboard context) and enforce company binding + manager scope independently of `/me`.
