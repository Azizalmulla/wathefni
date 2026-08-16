# Offer-1 Owner Review Package

**Environment:** staging only  
**Production touched:** no  
**Date:** 2026-07-18  

## Exact artifact SHA

```
b99e800dd6b9666af7b1fe788cd7ca760285fbab6d8d4f83baf9129cbdb3fe83
```

- Local rebuild hash: **match**
- `/opt/wathefni/staging/last-green.sha256`: **match**
- Staging service: **active**

## Smoke totals

| Suite | Result |
| --- | --- |
| Staging deploy smoke (`ops/staging-smoke.sh`) | **ALL PASSED** |
| Staging suite check lines (core tallies on green deploy) | **18 suites · 737 checks · 0 failed** |
| Offer-1 unit smoke (`smoke-test-offer-lifecycle.py`) | **passed** (included in preflight) |
| Owner-review harness (`ops/offer1-owner-review.py`) | **48 passed · 0 failed · 48 total** |

Owner-review section totals: artifact 2 · self_approval 3 · web_flow 7 · documents 5 · stale 1 · token 9 · hire_gate 2 · mobile 7 · ai 3 · override 7 · tenant 2.

## Checklist verdicts

| Requirement | Result |
| --- | --- |
| Web draft → submit → approve/return → send | PASS |
| Candidate token accept | PASS |
| Candidate token decline | PASS |
| Token expiry | PASS (`token_expired`) |
| One-time use | PASS (`token_used`) |
| Revocation on withdraw | PASS (`token_revoked`) |
| Stale/new-version token rejection | PASS (`version_mismatch`) |
| Hire unavailable before acceptance | PASS (`accepted_offer_required`) |
| Hire available only after accepted offer | PASS |
| Upload without match confirmation | PASS (`upload_match_confirmation_required`) |
| Upload with confirmation | PASS |
| Generated EN/AR documents | PASS (distinct SHA-256) |
| Mobile read / approve-return / record / withdraw | PASS |
| AI mutation rejection | PASS (`ai_forbidden`) |
| Grant-only override + reason + audit | PASS (on open offer → `employment_offer_events`) |
| Tenant isolation | PASS |
| Stale-version rejection | PASS (`stale_offer`) |
| No hidden self-approval (policy OFF) | PASS (`self_approval_forbidden`) |

## Document proof

| Locale | SHA-256 |
| --- | --- |
| EN | `175f3e4fc11de4b4449bc4f6a31b7e8ebb38782f7dda8ebc5d6f12638cd633da` |
| AR | `8eb651c00868f4b4b3af350b0a272bd1569ecca333b204f806d2c1512c5b752f` |

Files: `offer-en.pdf`, `offer-ar.pdf` in this folder.

## Screenshots

- `offer1-owner-review-board.png` — overall 48/48 board + SHA
- `offer1-document-proof.png` — EN/AR + upload mismatch
- `offer1-token-hire-proof.png` — token security + hire gate + separation

## Side effects (staging only)

Synthetic/fixture offers and tokens under company `WATHEFNI` (and isolation company `OWNERREVX` ensured). Applications may have been shortlisted for fixtures without prior accepted offers. Hire-override audit events written. No production writes. No real WhatsApp/email send (delivery `intentionally_skipped` in dry staging).

## Residual risk (non-blocking for owner accept, fix before or with first hotfix)

When `offer.hire_override` is used on an **app with no offer row**, the fallback `application_lifecycle_events` insert can silently fail if `actor_user_id` is not a UUID (`actor_user_id` column is uuid). Override **with an open/accepted offer present** audits correctly via `employment_offer_events`. Recommend hardening the no-offer fallback to use `NULL` actor or text-safe audit before relying on that edge path in production.

## Production promotion plan (do not run yet)

1. Confirm this owner package is accepted.
2. Optionally harden no-offer override audit (new artifact → re-stage → new green SHA).
3. Promote **exact** green SHA only: `ops/deploy.sh production` (gate compares artifact to `last-green.sha256`).
4. Enable `employment_offers` per tenant deliberately (module off = hire behavior unchanged).
5. Keep `offer_allow_self_approval` **false** unless a tenant explicitly opts in.
6. Grant `offer.hire_override` only via permission grants; never role defaults; never AI.
7. Post-promote synthetic proofs: owner-review subset + hire gate + token revoke on staging-equivalent company in prod canary.

## Rollback plan

1. Pre-deploy snapshot path is written by deploy to `/opt/wathefni/backups/.last-predeploy`.
2. `ops/deploy.sh rollback` restores last pre-deploy orchestrator + dashboard public snapshot.
3. Immediate mitigation without full rollback: disable `employment_offers` module for affected tenants (hire gate off; open offers remain readable but lifecycle gated by module checks).
4. Do not delete offer tables on rollback; schema is additive and safe to leave.

## Evidence index

- `OWNER_REVIEW_RESULTS.json` — machine-readable 48 checks
- `token-preview-after-accept.json` — public preview after one-time use
- PDFs + screenshots above
- Harness: `ops/offer1-owner-review.py`
