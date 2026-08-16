# Workspace smoothness — production deploy

**Verdict: PASS**  
**Stamp:** `20260801T030232Z`  
**Host:** `root@76.13.63.68`  
**Dashboard:** `https://api.wathefni.ai/dashboard/`  
**Scope:** Dashboard smoothness pass only (no orchestrator / API / permission changes)

## Production SHA

| Artifact | Value |
|----------|-------|
| Dashboard chunk | `dashboard-CmztGRNg.js` |
| Dashboard SHA-256 | `3afa9f3d6114cbcab80280e5dd610b66893c91f94f974c08b80f67bb9ee0ed42` |
| CandidatesPage | `CandidatesPage-CMHaxZSu.js` |
| ReportsPage | `ReportsPage-DX_-QeIm.js` |
| CalendarShell | `CalendarShell-Cfrjq7e2.js` |
| PostHire | `PostHire-BoHDU-E2.js` |

Qualified local SHA matched production after deploy (`sha_match: true`).

## Gates

| Gate | Result |
|------|--------|
| Health after deploy | **200** |
| No Overview Company → My flicker | **PASS** |
| No wrong page/nav flash (Jobs deep-link) | **PASS** |
| Candidates skeleton (not empty→real) | **PASS** |
| Reports skeleton (not empty→real) | **PASS** |
| Assessments `tab=reports` preserved after paint/nav | **PASS** |
| Calendar mobile no week→day snap | **PASS** |
| Post-hire Leave Active→History no stale rows | **PASS** |
| Hard refresh / back / forward | **PASS** |
| EN/AR + RTL | **PASS** |
| Desktop + mobile | **PASS** |
| Slow-network / delayed-API simulation | **PASS** |
| Targeted Vitest (30) | **PASS** |
| Production build markers | **PASS** |
| Rollback → restore-new | **PASS** |
| Health after restore | **200** |

## Screenshots

- `screenshots/prod-en-desktop-overview.png` — nav + content skeletons during bootstrap
- `screenshots/prod-en-desktop-candidates-skeleton.png` — list skeleton under delayed API
- `screenshots/prod-en-desktop-candidates.png` / `…-after.png` — settled list
- `screenshots/prod-en-desktop-reports-skeleton.png` — reports skeleton
- `screenshots/prod-en-desktop-reports.png` / `…-after.png`
- `screenshots/prod-en-desktop-assessments-reports.png`
- `screenshots/prod-en-mobile-calendar.png`
- `screenshots/prod-en-desktop-jobs.png`
- `screenshots/prod-en-desktop-leave.png`
- `screenshots/prod-en-desktop-interviews.png`
- `screenshots/prod-en-desktop-history-forward-reports.png`
- `screenshots/prod-ar-desktop-candidates-rtl.png`
- `screenshots/prod-ar-mobile-overview-rtl.png`

## Backup / rollback

- Backup: `/opt/wathefni/backups/production-pre-workspace-smoothness-20260801T030232Z`
- Scripts: `rollback/ROLLBACK.sh`, `rollback/RESTORE_NEW.sh`
- Exercise: rolled back to Wave4 `dashboard-Bt0QpWcY.js` (`3cf47ae1…`), then restored smoothness chunk; health 200 both ways

## Evidence

- Local: `/Users/azizalmulla/Desktop/claw/ops/evidence/workspace-smoothness-deploy-20260801T030232Z`
- Remote: `/opt/wathefni/production-evidence/workspace-smoothness/20260801T030232Z`
- Prior local qualification: `ops/evidence/workspace-smoothness-local-20260801T025618Z`

## Notes

- Existing URL authority, saved views, permissions, filters, and module behavior preserved (dashboard UI-only deploy).
- Focused delayed-API probes confirmed `candidates-list-skeleton` and `reports-skeleton` before rows/content (see `verify/prod-skeleton-probes.json`).
