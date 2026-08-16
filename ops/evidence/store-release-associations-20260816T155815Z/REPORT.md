# Production store association qualification

**Date:** 2026-08-16

**Target:** `https://api.wathefni.ai`

**Result:** `HTTPS_APP_LINKS_LIVE_PASS` — **90 passed, 0 failed** under exact expected-identifier qualification

## Deployment

The existing `wathefni-orchestrator.service` environment override was used. Only the orchestrator was restarted; product code, bundle/package IDs, and signing keys were unchanged.

- Apple application identifier: `ZZJ645575F.ai.wathefni.employee`.
- Android package: `ai.wathefni.employee`.
- Certificate set: all three supplied Google Play app-signing SHA-256 fingerprints; no upload-key fingerprint.
- Deployment backup: `/opt/wathefni/backups/store-release-associations-20260816T155815Z`.

No secret value is recorded in this report. Apple Team IDs, application IDs, Android package names, and certificate fingerprints are public association identifiers.

## Proof

- `/.well-known/apple-app-site-association`: direct HTTP 200, `application/json`, exact production App ID, exact paths `/l` and `/l/*`.
- `/.well-known/assetlinks.json`: direct HTTP 200, `application/json`, canonical package and relation, exact three-certificate set.
- Registered HTTPS routing: all 38 routes passed; unknown slugs fail closed.
- Standard release-harness association invocation: **89 passed, 0 failed**.
- Production `/health` and `/ready`: HTTP 200 after restart.
- Frozen R8 dimensions: environment binding, permission authority, trusted authority, link signing, delivery, recent errors, failed jobs, migrations, drift, forward-only policy, and rollback runbook all green.

The readiness contract and association match rules were not weakened.
