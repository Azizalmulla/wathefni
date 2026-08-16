# Assessments Cleanup-1 Production Controlled Promotion

**Date:** 2026-07-18  
**Status:** Production verified. Controlled promotion of staging-green artifact only. Stopped after verification.

## Production artifact SHA

```
bf638375b90b714da108d58dd8fc1b22bf2ffb361054a2988bcc547a78354ad6
```

- Staging-green gate: **matched** before promote
- Local deploy-formula recompute at promote: **matched**
- Source commit (workspace HEAD at promote): `390d2b2e3351816145ddf185b942982dba3cd330`
- `WATHEFNI_ASSESSMENT_AUTHORING`: **unset / off** on production service
- Live-bank publish: **blocked** (`assessment_authoring_disabled`)
- External tenant enablement: **unchanged**
- Item bank / scoring rules / norms content digests: **unchanged**

## Pre-deploy backup / rollback

| Item | Reference |
| --- | --- |
| Daily backup stamp | `20260718T102343Z` |
| Pre-deploy snapshot | `/opt/wathefni/backups/predeploy-20260718T102352Z` |
| Rollback pointer | `/opt/wathefni/backups/.last-predeploy` → `predeploy-20260718T102352Z` |
| Rollback command | `ops/deploy.sh rollback` |

## Migration (explicitly approved)

Confirm string: `production:wathefni:assessments_cleanup1_v1`  
Script: `ops/migrate-assessments-cleanup1-production.py` (outside artifact hash; staging migrate still refuses non-staging)

### First run

```json
{"attempts_seen": 4, "attempts_pinned": 4, "attempts_expired": 3, "responses_backfilled": 22, "scores_frozen": 1, "reports_frozen": 1, "events_added": 7, "historical_screening_json_changed": false, "item_bank_content_modified": false, "scoring_rules_modified": false, "norms_modified": false}
```

### Idempotent rerun

```json
{"attempts_seen": 4, "attempts_pinned": 0, "attempts_expired": 0, "responses_backfilled": 0, "scores_frozen": 0, "reports_frozen": 0, "events_added": 0}
```

## Real data before → after

### Pre-deploy inventory (before migrate)

| Metric | Value |
| --- | --- |
| assessment_attempts | 4 (1 completed, 3 pending) |
| assessment_responses | 22 |
| assessment_scores | 1 |
| assessment_reports | 1 |
| assessment_version_id column | absent |

### Post-migrate / post-proof (WATHEFNI real counters)

| Counter | Before proof → After proof |
| --- | --- |
| applications | 17 → 17 |
| interviews | 4 → 4 |
| offers | 0 → 0 |
| employees | 4 → 4 |
| outbound_delivery_events | 5 → 5 |
| assessment_scores | 1 → 1 |
| assessment_items | 22 → 22 |
| assessment_attempts | 4 → 4 |
| assessment_attempts_pinned | 4 → 4 |
| assessment_attempts_expired | 3 → 3 |
| item / scoring / norms digests | unchanged |

Intended migrate-only changes vs pre-deploy: 4 attempts pinned, 3 pending→expired, 22 responses version-backfilled, 1 score + 1 report frozen. No real WhatsApp/email sent.

## Production smoke totals

| Suite | Result |
| --- | --- |
| Local preflight (dashboard vitest + offer smokes) | passed (38 dashboard tests) |
| `ops/deploy.sh production` + public-route guard | **OK** / health 200 |
| Production migration | **ok** + idempotent zero rerun |
| Production synthetic proof (`ops/assessments-cleanup1-production-proof.py`) | **44 passed · 0 failed · 44 total** |

## Synthetic cleanup proof

All `ASSESSP1A` / `ASSESSP1B` fixtures removed:

- attempts / drafts / applications / modules / companies / candidates (`96571001*` / `96571002*`) → **0**

Delivery during proof: mocked `intentionally_skipped` / `WATHEFNI_DELIVERY_MODE=dry_run`.  
`real_delivery_sent`: **false**

## Confirmation

Real applications, interviews, offers, employees, assessment scores, outbound counters, and item-bank/scoring/norms content were **unchanged** except for the intended attempt migration (pin / expire / response backfill / freeze).

## Evidence index

- `assessments-cleanup1-prod-before.json`
- `assessments-cleanup1-prod-migrate.json`
- `assessments-cleanup1-prod-migrate-rerun.json`
- `assessments-cleanup1-prod-proof.json`
- `production-deploy.log`
- `HASHES.txt`

## Stop

Production promotion and verification complete. No further production changes in this package.
