# Assessments Cleanup-1 Owner Review Package

**Environment:** staging only  
**Production touched:** no  
**Date:** 2026-07-18  

## Exact artifact SHA

```
bf638375b90b714da108d58dd8fc1b22bf2ffb361054a2988bcc547a78354ad6
```

- `/opt/wathefni/staging/last-green.sha256`: **match**
- Local `ops/deploy.sh` artifact formula recompute (absolute dashboard paths): **match**
- Staging orchestrator + dashboard **content hashes**: match evidence / local dist
- Staging service: **active** · health **200**
- Artifact was **not** modified for this review

## Owner-review test total

| Suite | Result |
| --- | --- |
| Cleanup-1 authority smoke (re-run, no redeploy) | **29 passed · 0 failed** |
| Migration inventory + idempotent rerun | **5 passed · 0 failed** |
| Artifact / staging-green / prod isolation | **3 passed · 0 failed** |
| **Owner-review total** | **37 passed · 0 failed · 37 total** |

Authority section coverage: idempotency · concurrency · cancel/expire/complete rejection · resend/revoke · tenant/WhatsApp · version pin · immutability · screening facet separation · ranking · queue parity · exact report · authoring gate · offer/hire non-coupling.

## Checklist verdicts

| Requirement | Result |
| --- | --- |
| Duplicate answer submission does not advance twice | PASS |
| Concurrent browser submissions remain safe | PASS |
| Cancelled attempts reject further answers | PASS |
| Expired attempts reject further answers | PASS |
| Completed attempts reject mutation | PASS |
| Resend creates correct delivery/token behavior | PASS |
| Old links revoked when required | PASS |
| HR cancellation works and is audited | PASS |
| Tenant isolation (application/attempt/candidate/WhatsApp) | PASS |
| Attempt pinned to immutable battery/item version | PASS |
| Completed responses/scores/reports cannot be overwritten | PASS |
| Assessment completion does not write fake screening completion | PASS |
| Pending/in-progress assessments earn no positive ranking credit | PASS |
| `ready_for_review` count and queue match | PASS |
| Exact report opens from candidate drawer | PASS |
| Mobile shows the same authoritative assessment state | PASS |
| Offer-1 and hire authority remain unaffected | PASS |
| AI cannot alter questions, answer keys, scores, norms, or candidate decisions | PASS |

## Migration proof

| Metric | First migrate (recorded) | Owner-review rerun |
| --- | --- | --- |
| Attempts seen | 4 | 4 |
| Attempts pinned | 4 | **0** |
| Attempts expired | 3 | **0** |
| Responses backfilled | 22 | **0** |
| Scores frozen | 1 | **0** |
| Reports frozen | 1 | **0** |
| Events added | 7 | **0** |
| Historical screening changed | false | false |

Live staging inventory now: **4 pinned** (1 completed + 3 expired), **22** versioned responses, **1** immutable score + **1** immutable report, all on content version `4bfa5a53-77bf-4102-9a6c-ffa079a90c3e`.

Completed production-shaped sample `96598900677-WATHEFNI-ACCOUNTING`: assessment `completed` / report frozen; screening facet still `complete` with `screening_completed_at=2026-05-05` (not rewritten by assessment completion).

## Screenshots

- `cleanup1-owner-review-board.png` — 29/29 authority board + SHA
- `cleanup1-migration-proof.png` — 4/3/22/1 + zero-change rerun
- `cleanup1-surface-proof.png` — web queue / exact report / mobile / offer-hire separation

## Side effects (staging only)

Cleanup-1 smoke creates and deletes synthetic tenants (`ASSESSC1A` / `ASSESSC1B`); owner-review re-run left **synthetic_cleanup empty**. Migration rerun made **zero** writes. Delivery remains `dry_run` / `intentionally_skipped`. No production writes. Production tree has **no** `assessment_lifecycle.py` and **no** Cleanup-1 migrate script.

## Remaining defects (non-blocking for staging accept)

1. **Artifact hash path sensitivity** — `deploy.sh` includes absolute dashboard paths in the hash stream. Content on staging matches green; remote path-based recompute will differ. Normalize to content-only hashing before the next promotion wave.
2. **Authoring flag** — `WATHEFNI_ASSESSMENT_AUTHORING=true` is staging-only. Keep it **off** for production until a dedicated authoring cutover is approved. Live-bank publish remains blocked even when the flag is on.

## Production promotion plan (do not run yet)

1. Owner accepts this package for artifact `bf638375…78354ad6` only.
2. Keep production authoring flag **off**.
3. Promote **exact** green SHA via `ops/deploy.sh production` (gate compares local artifact to `/opt/wathefni/staging/last-green.sha256`).
4. Run production-safe Cleanup-1 migration only after an explicit production migration approval (current migrate script **refuses non-staging** and must be extended/replaced for prod).
5. Post-promote canary: duplicate-answer idempotency, cancel/expire rejection, resend revoke, exact report open, ranking zero for incomplete, offer/hire unchanged.
6. Do not enable AI live-bank publish.

## Rollback plan

1. Pre-deploy snapshot path is written by deploy to `/opt/wathefni/backups/.last-predeploy`.
2. `ops/deploy.sh rollback` restores last pre-deploy orchestrator + dashboard public snapshot.
3. Immediate mitigation without full rollback: disable `assessments` module for affected tenants (queue/actions hide; frozen historical rows remain readable).
4. Do not delete assessment version/immutability columns on rollback; schema is additive and safe to leave.
5. If a production migrate is later applied, roll forward with a compensating freeze script rather than deleting score/report rows.

## Evidence index

- `OWNER_REVIEW_RESULTS.json` — machine-readable 37 checks + checklist
- Screenshots above
- Parent proof: `../PROOF.json`, `../HASHES.txt`
- Harness: `wathefni-orchestrator/smoke-test-assessments-cleanup1.py`
- Migrate: `wathefni-orchestrator/ops/migrate-assessments-cleanup1.py`

**Stop before production.**
