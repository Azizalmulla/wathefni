# Shifts week/day navigation soft-keep — production deploy

**Stamp:** `20260804T183521Z`  
**Bundle:** `PostHire-D7Xyr7Nk.js`  
**Status:** Production proof green. Shifts is **not frozen** until product sign-off on the live transition.

## What shipped

- Soft-keep last committed board (tiles, day headers, range label, dimensions) while the next range loads.
- No blank wipe, opacity flash, or full remount during navigation.
- Atomic replace only when the latest request matches the current target (`commitIfLatest`).
- Slower older responses are dropped.
- Week payload cache + ±1 adjacent prefetch; day view filters the week client-side.
- Filters, Day/Week mode, drawer selection, and scroll position preserved across commits.
- Updating rail while pending/refreshing.
- Fixed `reloadFresh` → invalidate cache then `reload()` (was recursive).

## Production proof

| Check | Result |
| --- | --- |
| Bundle markers | `NAV_SOFT_KEEP_SMOKE_OK` (`PostHire-D7Xyr7Nk.js`) |
| Rapid next burst soft-keep | `pending=true`, **47** tiles retained, label stays `Aug 16–22` while `target_week=9` |
| Soft-keep blanks | `0` |
| Race settle | `committed_week == target_week` (`9`) after burst |
| Prev soft-keep | pending frame retained 7 tiles while target moved |
| Delayed GETs | `14+` |
| IQ-12 recheck | `SHIFTS_WAVE2_IQ_SMOKE_OK` |

Request-race report: `after/nav-race-report.json`  
Sequential screenshots: `after/01-start-populated.png` … `after/10-seq-settled.png`

## Paths

- Local evidence: `ops/evidence/shifts-nav-soft-keep-prod-deploy-20260804T183521Z/`
- Remote evidence: `/opt/wathefni/production-evidence/shifts-nav-soft-keep/20260804T183521Z/`
- Contracts: `apps/wathefni-dashboard/src/posthire/ShiftsBoardRangeContract.test.ts`

## Rollback

```bash
/opt/wathefni/backups/production-pre-shifts-nav-soft-keep-20260804T183521Z/ROLLBACK.sh
```

Restores prior dashboard dist to `/opt/wathefni/dashboard-dist` and `/var/www/wathefni-dashboard`.

## Freeze gate

**Do not freeze Shifts** until product confirms rapid prev/next feels smooth on production. Soft-keep + race integrity are proved; freeze is a product call.
