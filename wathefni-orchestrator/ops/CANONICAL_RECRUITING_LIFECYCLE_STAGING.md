# Canonical Recruiting Lifecycle — Staging Proof

**Status:** Implemented behind `WATHEFNI_CANONICAL_LIFECYCLE` (staging ON, production OFF).  
**Date:** 2026-07-15  
**Stop point:** Staging proof only — wait for approval before production.

## What shipped

| Piece | Location |
|---|---|
| Transition authority | `recruiting_lifecycle.py` |
| Schema migration | `ensure_lifecycle_schema()` via `ensure_schema(force=True)` |
| Tables / indexes | `application_lifecycle_events`, `conversation_application_bindings`, unique open ready-task index on `hr_tasks` |
| Flag | `WATHEFNI_CANONICAL_LIFECYCLE` — staging unit sets `true`; production unset/OFF |
| Smoke | `smoke-test-canonical-recruiting-lifecycle.py` (also in `ops/staging-smoke.sh`) |
| Web/mobile label proof | `apps/wathefni-dashboard/src/lib/lifecycle-labels.test.ts` |

## Application stages

`awaiting_cv → cv_processing → ready_for_review → shortlisted → interview → hired`  
Terminal alternatives: `rejected`, `withdrawn`

## Legacy mapping

| Legacy | Canonical |
|---|---|
| `cv_received`, `screening` | `cv_processing` |
| `screening_complete`, `review_pending` | `ready_for_review` |
| `offered`, `offer_sent` | `shortlisted` (read alias; no offer lifecycle) |
| `scheduled` | `interview` |
| `needs_role`, `import_review`, `import_archived` | intake facet (not application stage) |

## Production rollout recommendation

1. Keep production flag **OFF** until this staging proof is approved.
2. After approval: enable `WATHEFNI_CANONICAL_LIFECYCLE=true` on production via feature-flags drop-in (not in the unit file permanently until soak).
3. Deploy production only via `ops/deploy.sh production` after this staging artifact is green.
4. Do **not** backfill-rewrite historical statuses in the first prod cut — read path uses legacy mapping; writes use canonical stages.
5. Monitor: lifecycle event volume, ready-for-review task dedupe, WhatsApp ambiguity replies, reject permission denials for recruiters.
6. Rollback: unset/remove the flag; schema tables are additive and safe to leave.
