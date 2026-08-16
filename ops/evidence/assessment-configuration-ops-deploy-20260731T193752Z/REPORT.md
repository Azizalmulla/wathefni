# Assessment configuration ops — production deploy

**Stamp:** `20260731T193752Z`  
**Host:** `root@76.13.63.68`  
**Dashboard:** `https://api.wathefni.ai/dashboard/`  
**Qualified local pack:** `/Users/azizalmulla/Desktop/claw/ops/evidence/assessment-configuration-ops-20260731T192953Z`  
**Live chunk:** `dashboard-C2UeV2r7.js`  
**Artifact SHA-256:** `eb634c49d58658b242e62984567505875be3cdc913c87360344ce6419a218196`  
**Verdict:** **PASS**

## Scope deployed
- Rename → Assessment configuration
- Collapsed by default + summary row (ready / questions / evidence / last refreshed)
- Expanded admin grid + Refresh setup
- `canSeeSetup` preserved (recruiter/HM excluded in live chunk)
- Product2 left as-is
- No Settings move; no logic/permission/contract/queue changes

## Production gates

| Gate | Result |
|---|---|
| Health after | **200** |
| Dashboard after | **200** |
| Live chunk + index ref | **PASS** (`dashboard-C2UeV2r7.js`) |
| Artifact SHA-256 | `eb634c49d58658b242e62984567505875be3cdc913c87360344ce6419a218196` |
| Collapsed default (prod) | **PASS** |
| Expand/collapse works | **PASS** |
| Admin grid permission-gated (role strings) | **PASS** |
| EN/AR + RTL | **PASS** |
| Send / Attempts / Reports unchanged | **PASS** |
| Targeted Vitest | **PASS** 10/10 |
| Rollback verified (old → new restore) | **PASS** |

## Screenshots
- `screenshots/after/prod-assessments-en-collapsed.png`
- `screenshots/after/prod-assessments-en-expanded.png`
- `screenshots/after/prod-assessments-ar-collapsed.png`
- `screenshots/after/prod-assessments-ar-expanded.png`
- `screenshots/after/prod-assessments-en-attempts.png`
- `screenshots/after/prod-assessments-en-reports.png`
- Rollback: `screenshots/rollback-check/`

## Backup / rollback
- Backup: `/opt/wathefni/backups/production-pre-assessment-configuration-ops-20260731T193752Z`
- Local copy: `/Users/azizalmulla/Desktop/claw/ops/evidence/assessment-configuration-ops-deploy-20260731T193752Z/ROLLBACK.sh`

## Evidence path
`/Users/azizalmulla/Desktop/claw/ops/evidence/assessment-configuration-ops-deploy-20260731T193752Z`
