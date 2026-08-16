# Candidates filter UX Wave 4 — production deploy

**Verdict: PASS**  
**Stamp:** `20260801T023636Z`  
**Host:** `root@76.13.63.68`  
**Dashboard:** `https://api.wathefni.ai/dashboard/`  

## Production SHA
| Artifact | Value |
|----------|-------|
| Dashboard chunk | `dashboard-Bt0QpWcY.js` |
| Dashboard SHA-256 | `3cf47ae1c69f3f998dd469ca19f918db4a41a5f491d6f8eef3a6fa0b62524285` |
| CandidatesPage chunk | `CandidatesPage-LD6meTzs.js` |

## Scope shipped
- Default bar: Search, Job, Stage, Filters (N)
- Active removable chips including Follow-up needed
- Desktop side drawer + mobile full-height sheet
- Clear all in chip row and drawer footer
- Open/close preserves filter state
- Predicates / URL authority / saved views / counts / permissions / tenant isolation unchanged

## Gates
| Gate | Result |
|------|--------|
| Health after | **200** |
| Desktop drawer | **PASS** |
| Mobile sheet | **PASS** |
| EN/AR + RTL | **PASS** |
| Active-filter count accurate | **PASS** |
| Chips remove only own filter/context | **PASS** |
| Clear all | **PASS** |
| Reload / back-forward preserve filters | **PASS** |
| Saved views | **PASS** |
| Targeted Vitest (40) | **PASS** |
| Rollback → restore-new | **PASS** |

## Screenshots
- `screenshots/prod-en-desktop-chips.png`
- `screenshots/prod-en-desktop-drawer.png`
- `screenshots/prod-en-mobile-sheet.png`
- `screenshots/prod-ar-desktop-chips-rtl.png`
- `screenshots/prod-ar-mobile-sheet-rtl.png`

## Backup / rollback
- Backup: `/opt/wathefni/backups/production-pre-candidates-filter-ux-wave4-20260801T023636Z`
- Scripts: `ROLLBACK.sh`, `RESTORE_NEW.sh`

## Evidence
- Local: `/Users/azizalmulla/Desktop/claw/ops/evidence/candidates-filter-ux-wave4-deploy-20260801T023636Z`
- Remote: `/opt/wathefni/production-evidence/candidates-filter-ux-wave4/20260801T023636Z`
