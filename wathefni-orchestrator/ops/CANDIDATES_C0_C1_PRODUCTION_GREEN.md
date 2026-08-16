# Candidates C0/C1 — production-green / frozen

**Status:** production-green, frozen  
**Pinned at:** 2026-07-21T19:49:49Z  
**Do not begin C2/C3 implementation until separately approved.**

## Pins

| Item | Value |
|---|---|
| Commit | `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2` |
| Artifact SHA | `f17ff4d3b773027c583e8dc9baac4aa21842dd7b41d92525eced7e3d2e664729` |
| Staging-green | same artifact (exact promote) |
| VPS freeze JSON | `/opt/wathefni/orchestrator/ops/reports/candidates-c01-production-green.json` |

### Staging-qualified overlays beyond the commit

These two deltas were part of the owner-UX-passed staging-green artifact and were promoted with it:

1. `operator_mobile.py` — assessments advisory read capability
2. `ImportCenter.tsx` — CV preview in import review queue

No other CODE_FILES differed from `40a4e26`.

## Production identity

| Item | Value |
|---|---|
| Service | `wathefni-orchestrator.service` (:8010) |
| Database | `wathefni` / `wathefni_app` |
| Marker | `wathefni-production-isolation-v1` |
| Workspace | `/root/.openclaw/workspaces/company-wathefni` |
| Dashboard | `/var/www/wathefni-dashboard` (`dashboard-DtlYUEnJ.js`) |
| Canonical lifecycle | `WATHEFNI_CANONICAL_LIFECYCLE=true` |

## Backup / rollback

| Item | Path |
|---|---|
| Explicit verified dump | `/opt/wathefni/backups/candidates-c01-production-predeploy-20260721T194311Z/wathefni.dump` (TOC 800 lines) |
| Daily backup | `/opt/wathefni/backups/daily/20260721T194311Z` (+ deploy-time `20260721T194419Z`) |
| Code/dashboard snapshot | `/opt/wathefni/backups/predeploy-20260721T194425Z` |

```bash
# Code + dashboard rollback to last predeploy snapshot
bash ops/deploy.sh rollback
```

Schema is additive (`lifecycle_version`, confirmation/lifecycle/hire tables, authority trigger, unique indexes). Rollback restores code/dashboard; new tables/indexes remain unless explicitly dropped.

## Schema applied

- `applications.lifecycle_version`
- `application_lifecycle_events` (+ idempotency)
- `candidate_action_confirmations`
- `hire_operations`
- trigger `applications_lifecycle_authority_guard` (enabled)
- `applications_one_active_same_role_uq`
- `employees_company_app_key_uq`

## Post-deploy proof

| Suite | Result |
|---|---|
| Production C0/C1 matrix | **44/44 PASS** |
| Canonical lifecycle smoke | **78/78 PASS** |
| Mobile authority | **55/55 PASS** |
| Local unit authority | **12/12 PASS** |
| Dashboard tests/build (deploy preflight) | **49/49 + build PASS** |
| Half-hires / same-role / dup employee links | **0 / 0 / 0** |
| Health (backend/dashboard/workers) | **200 / active** |

## Next

Candidates **C2 assessment only** — no implementation until owner approval.
