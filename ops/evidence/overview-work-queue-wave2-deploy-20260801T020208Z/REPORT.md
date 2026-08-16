# Overview work-queue Wave 2 — production deploy

**Verdict: PASS**  
**Stamp:** `20260801T020208Z`  
**Host:** `root@76.13.63.68`  
**Dashboard:** `https://api.wathefni.ai/dashboard/`  
**Wave 3:** not started  
**Candidates filters:** unchanged

## Production SHA
| Artifact | Value |
|----------|-------|
| Dashboard chunk | `dashboard-CpBtsbVO.js` |
| Dashboard SHA-256 | `b2b902f24b559143bc926a60c4c9aa055c18e0d157c9e30f29a9bb0eb3ac5c57` |
| Lifecycle chunk | `recruitingLifecycle-DXQht60b.js` |
| Lifecycle SHA-256 | `0b73b977b2f54e03135fc06727fba74318caf51c15b657ba74165605a2b3483b` |

## Scope shipped
- Removed miswired top-level View all beside My work / Company work
- Preserved My/Company scope toggle (`scope=mine|company`)
- Preserved row CTAs + attention-card deep links
- People primary unit; applications shown when different (live: **2 people · 4 applications**)
- Footer `N shown · M people`
- Multi-app rows use `N applications`

## Gates
| Gate | Result |
|------|--------|
| Health after | **200** |
| Dashboard after | **200** |
| No top-level View all in work section | **PASS** |
| Roles View all retained | **PASS** |
| My/Company API scope | **PASS** |
| Row CTA opens destination | **PASS** |
| Follow-up card → follow-up cohort | **PASS** |
| 2 people / 4 applications clear | **PASS** |
| EN/AR + RTL | **PASS** |
| Targeted Vitest (16) | **PASS** |
| Rollback exercise (old → restore new) | **PASS** |

## Backup / rollback
- Backup: `/opt/wathefni/backups/production-pre-overview-work-queue-wave2-20260801T020208Z`
- Scripts: `ROLLBACK.sh`, `RESTORE_NEW.sh`

## Evidence
- Local: `/Users/azizalmulla/Desktop/claw/ops/evidence/overview-work-queue-wave2-deploy-20260801T020208Z`
- Remote: `/opt/wathefni/production-evidence/overview-work-queue-wave2/20260801T020208Z`
