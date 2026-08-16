# Employee Onboarding Wave 2A — Mobile projection fix

**Stamp:** `20260805T045200Z`

## Root cause
API already returned correct Wave 2A groups (`lifecycle_version=2a`). Client could fall through to legacy `pending` / `received` aliases. Server alias `received = completed + being_reviewed`, which put Job offer under **Submitted** and hid the true sections.

## Fix
- `lifecycleProjection.ts` maps **only** `your_actions` / `being_reviewed` / `handled_by_others` / `completed`
- Status chips use `item.status` via `onboardingStatusLabel` (never `review_status`)
- No silent legacy fallback; contract mismatch surfaces an error
- Safe contract logging (`onboarding_wave2a_contract`) without PII/file bytes

## Aziz known states (prod smoke)
| item | status | section |
|---|---|---|
| civil_id | accepted | completed |
| employment_contract | replacement_required + reason + resubmit | your_actions |
| personal_photo | processing | being_reviewed |
| offer_letter | processing | being_reviewed (not Submitted) |

## Activation (fresh)
- phone field: `99338566`
- code: `156689`
- invite: `43e0c33c-291d-414d-b33f-37fc7ca57b9a`

## Build
Production-profile internal iOS — see EAS logs after stamp (build auto-increment).
