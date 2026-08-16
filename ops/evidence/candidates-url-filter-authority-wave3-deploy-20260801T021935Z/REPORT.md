# Candidates URL / filter-state authority Wave 3 — production deploy

**Verdict: PASS**  
**Stamp:** `20260801T021935Z`  
**Host:** `root@76.13.63.68`  
**Dashboard:** `https://api.wathefni.ai/dashboard/`  
**Wave 4:** not started  

## Production SHA
| Artifact | Value |
|----------|-------|
| Dashboard chunk | `dashboard-B_fWNxcn.js` |
| Dashboard SHA-256 | `ec1df8bb80370987a7019b41cecaaed6b6f89b6de3f0d44bc186293a6b3d6245` |

## Scope shipped
- Durable Candidates URL for meaningful flat filters (stage, view, advanced flat fields, cohort context)
- Follow-up clear drops `follow_up`, `overview_cohort`, `cohort_key`, `action`
- Saved-view select replaces (no stale cohort merge)
- Classification remains saved-view/session only
- Filter UI / backend predicates / permissions / tenant isolation unchanged

## Gates
| Gate | Result |
|------|--------|
| Health after | **200** |
| Dashboard after | **200** |
| Reload preserves active filters | **PASS** |
| Back/forward restores filters | **PASS** |
| Shared URLs reproduce results | **PASS** |
| Saved-view replaces stale cohort | **PASS** |
| Clear Follow-up clears quartet | **PASS** |
| Unrelated filters intact | **PASS** |
| EN/AR + RTL | **PASS** |
| Targeted Vitest (35) | **PASS** |
| Rollback → restore-new | **PASS** |

## Backup / rollback
- Backup: `/opt/wathefni/backups/production-pre-candidates-url-wave3-20260801T021935Z`
- Scripts: `ROLLBACK.sh`, `RESTORE_NEW.sh`

## Evidence
- Local: `/Users/azizalmulla/Desktop/claw/ops/evidence/candidates-url-filter-authority-wave3-deploy-20260801T021935Z`
- Remote: `/opt/wathefni/production-evidence/candidates-url-wave3/20260801T021935Z`
