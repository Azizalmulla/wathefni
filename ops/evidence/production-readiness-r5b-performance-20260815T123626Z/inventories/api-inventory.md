# R5B API inventory

Authenticated adapters only. Company and actor identity come from `dashboard_context` / `employee_app_context`. Clients never supply company or employee authority.

## HR / Manager — `/dashboard/performance/...`

| Method | Path | Family |
|---|---|---|
| GET | `/dashboard/performance/workspace` | workspace / summary |
| GET | `/dashboard/performance/objectives` | objectives / goals |
| GET | `/dashboard/performance/objectives/{objective_id}` | objectives / goals |
| GET | `/dashboard/performance/objectives/{objective_id}/history` | history / version |
| POST | `/dashboard/performance/objectives` | objectives / goals |
| POST | `/dashboard/performance/objectives/{objective_id}/key-results` | KRs |
| POST | `/dashboard/performance/objectives/{objective_id}/activate` | objectives / goals |
| GET | `/dashboard/performance/measures` | KRs / measures |
| POST | `/dashboard/performance/measures` | KRs / measures |
| POST | `/dashboard/performance/progress` | KRs / progress |
| GET | `/dashboard/performance/cycles` | cycles |
| GET | `/dashboard/performance/cycles/{cycle_id}` | cycles |
| GET | `/dashboard/performance/cycles/{cycle_id}/snapshot` | cycle snapshot (HR) |
| POST | `/dashboard/performance/cycles` | cycles |
| POST | `/dashboard/performance/cycles/{cycle_id}/configure` | cycles |
| POST | `/dashboard/performance/cycles/{cycle_id}/launch` | cycles / launch freeze |
| POST | `/dashboard/performance/cycles/{cycle_id}/close` | final / sealed |
| GET | `/dashboard/performance/scales` | cycle config |
| POST | `/dashboard/performance/scales` | cycle config |
| GET | `/dashboard/performance/templates` | cycle config |
| POST | `/dashboard/performance/templates` | cycle config |
| GET | `/dashboard/performance/reviews` | reviews |
| GET | `/dashboard/performance/reviews/{review_id}` | reviews / self / manager / 360 |
| POST | `/dashboard/performance/reviews/{review_id}/submit` | self / manager / 360 |
| GET | `/dashboard/performance/360` | 360 requests / responses |
| GET | `/dashboard/performance/competencies` | competencies / evidence |
| GET | `/dashboard/performance/feedback` | feedback (alias of check-ins) |
| GET | `/dashboard/performance/check-ins` | check-ins |
| GET | `/dashboard/performance/check-ins/{check_in_id}` | check-ins |
| POST | `/dashboard/performance/check-ins` | check-ins |
| POST | `/dashboard/performance/check-ins/{check_in_id}/complete` | check-ins |
| GET | `/dashboard/performance/development` | development actions |
| POST | `/dashboard/performance/development/plans` | development actions |
| POST | `/dashboard/performance/development/actions` | development actions |
| POST | `/dashboard/performance/development/actions/{action_id}/advance` | development actions |
| GET | `/dashboard/performance/calibration` | calibration |
| POST | `/dashboard/performance/calibration` | calibration |
| GET | `/dashboard/performance/calibration/{session_id}` | calibration |
| POST | `/dashboard/performance/calibration/{session_id}/adjust` | calibration |
| POST | `/dashboard/performance/calibration/{session_id}/lock` | sealed final |
| GET | `/dashboard/performance/manager/queue` | manager review queue |

## Thin HR Mobile — `/dashboard/mobile/performance/...`

| Method | Path | Family |
|---|---|---|
| GET | `/dashboard/mobile/performance` | pending review queue |
| GET | `/dashboard/mobile/performance/reviews/{review_id}` | review detail |
| POST | `/dashboard/mobile/performance/reviews/{review_id}/submit` | approve / submit |

## Employee — `/app/performance/...`

| Method | Path | Family |
|---|---|---|
| GET | `/app/performance` | workspace / summary |
| GET | `/app/performance/objectives` | my goals |
| GET | `/app/performance/objectives/{objective_id}` | objective / KR detail |
| POST | `/app/performance/progress` | check-in / progress (owned only) |
| GET | `/app/performance/reviews` | my reviews |
| GET | `/app/performance/reviews/{review_id}` | self-review / requested 360 |
| POST | `/app/performance/reviews/{review_id}/submit` | self / 360 submit (not manager) |
| GET | `/app/performance/feedback` | feedback |
| GET | `/app/performance/check-ins` | check-ins |
| GET | `/app/performance/development` | development actions |

## Explicitly not exposed

- Raw C1–C4 Python library operations
- Client-supplied `company_code` / employee authority as write identity
- Talent / HiPo / potential / succession / 9-box / Talent score
- Calibration administration on employee or HR Mobile namespaces
- Public unauthenticated Performance endpoints
