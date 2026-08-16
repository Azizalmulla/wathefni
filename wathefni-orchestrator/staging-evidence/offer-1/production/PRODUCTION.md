# Offer-1 Production Controlled Promotion

**Date:** 2026-07-18  
**Status:** Production verified. Controlled enablement only for WATHEFNI. Stopped after verification.

## Production artifact

```
44c02407bdbf6484c9bb35ec44b0d841a0451cb52ee64261779ee67f2bbbd13c
```

- Source commit (Offer-1 hire-override harden package): `8ada28e7a14068252eaea3aaa455fdb771e5c9f4`
- Staging-green gate: **matched** before promote
- Local rebuild hash at promote: **matched**
- Prior artifact: **not** promoted

## Backup / rollback

| Item | Reference |
| --- | --- |
| Pre-deploy snapshot | `/opt/wathefni/backups/predeploy-20260718T010911Z` |
| Daily backup stamp | `20260718T010908Z` |
| Rollback | `ops/deploy.sh rollback` (restores `.last-predeploy`) |

## File hashes (promoted)

See `HASHES.txt`. Key offer files:

| File | sha256 |
| --- | --- |
| offer_lifecycle.py | efae44a80504d0ea7f5b6ac92a8da5c0482142ead153db35537c99a56fdcf311 |
| offer_service.py | a7d8f8e605179333d8ef10ea85bdb6a167b724dbed68dea4662d42d17e105bc6 |
| offer_routes.py | 914c5975dc3b5f10bd6eadc4deb29259ad6638321290d4e6cb85cfdefe95e7b8 |

## Migration

`ensure_schema` / prod migrate: **ok** (`prod schema ok`). Tables present:

- employment_offers
- employment_offer_versions
- employment_offer_events
- employment_offer_tokens
- employment_offer_deliveries
- employment_offer_hire_override_audits

## Tenant / module state

| Setting | State |
| --- | --- |
| WATHEFNI `employment_offers` | **enabled** (controlled production proof) |
| External tenants `employment_offers` | **all disabled** (0 others enabled) |
| `offer_allow_self_approval` | **false** (default SoD) |
| Real WhatsApp/email in proof | **none** — delivery `intentionally_skipped` |

## Smoke totals

| Suite | Result |
| --- | --- |
| Local preflight (dashboard tests + offer smokes) | passed |
| Production deploy + public-route guard | **OK** / health 200 |
| Production synthetic proof (`ops/offer1-production-cutover-proof.py`) | **45 passed · 0 failed · 45 total** |

## Synthetic cleanup proof

All marker fixtures removed after proof:

- offers / tokens / deliveries / events / versions / override audits / applications / candidates for `OFFER1PROD-*`
- Probe company `OFFER1XO` removed

## Real WATHEFNI counters unchanged

| Counter | Before → After |
| --- | --- |
| applications | 17 → 17 |
| interviews | 4 → 4 |
| employees | 4 → 4 |
| outbound_delivery_events | 5 → 5 |

## Stop

Production verification complete. No further rollout steps taken.
