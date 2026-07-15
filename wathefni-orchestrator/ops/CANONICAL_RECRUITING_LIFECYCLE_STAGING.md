# Canonical Recruiting Lifecycle — Staging Proof

**Status:** Staging DB proof PASSED (77/77). Production remains OFF.  
**Commits:** `fa9e94d`, `6d8bf32` on branch `authority-cutover`  
**Date:** 2026-07-15

## Staging evidence

| Check | Result |
|---|---|
| Schema `application_lifecycle_events` | created via `ensure_schema` |
| Schema `conversation_application_bindings` | created |
| Unique open ready-task index | created |
| `WATHEFNI_CANONICAL_LIFECYCLE` on staging unit | `true` |
| Smoke `smoke-test-canonical-recruiting-lifecycle.py` on staging DB | **77 passed, 0 failed** |
| Web/mobile label consistency vitest | **4 passed** |
| Local preflight (matrix/labels/permissions) | passed |

Full `ops/deploy.sh staging` suite also advanced through prehire/CV/employee smokes; it later failed on unrelated `smoke-test-leave-standalone.py` (`permission_denied` on `request_leave`). Lifecycle proof was re-run directly against the staging DB after that and passed cleanly.

## Application stages

`awaiting_cv → cv_processing → ready_for_review → shortlisted → interview → hired`  
Terminal alternatives: `rejected`, `withdrawn`

## Transition matrix (enforced)

| From | Allowed to |
|---|---|
| awaiting_cv | cv_processing, withdrawn, rejected |
| cv_processing | ready_for_review, awaiting_cv, withdrawn, rejected |
| ready_for_review | shortlisted, interview, rejected, withdrawn |
| shortlisted | interview, hired, rejected, withdrawn, ready_for_review |
| interview | shortlisted, hired, rejected, withdrawn |
| hired / rejected / withdrawn | (terminal) |

## Legacy-status mapping

| Legacy | Canonical |
|---|---|
| cv_received, screening | cv_processing |
| screening_complete, review_pending | ready_for_review |
| offered, offer_sent | shortlisted (read alias only) |
| scheduled | interview |
| needs_role, import_review, import_archived | intake facet (not stage) |

## Communication states

`pending` | `sent` | `failed` | `intentionally_skipped`

## Production rollout recommendation

1. **Do not enable production yet.** Wait for explicit approval.
2. After approval: enable `WATHEFNI_CANONICAL_LIFECYCLE=true` only after a clean full staging suite (or accept leave-smoke triage separately).
3. Promote via `ops/deploy.sh production` gated on staging-green hash.
4. First prod cut: flag on, **no bulk status rewrite** — reads use legacy mapping; new writes use canonical stages.
5. Monitor: lifecycle events, ready-task dedupe, WhatsApp ambiguity replies, recruiter reject denials (`candidate.decide`).
6. Rollback: unset the flag. Additive tables/indexes are safe to leave.
