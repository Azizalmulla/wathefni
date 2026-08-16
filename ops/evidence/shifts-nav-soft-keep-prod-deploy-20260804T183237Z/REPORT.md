# Shifts week/day navigation soft-keep — production deploy

**Stamp:** `20260804T183237Z`  
**Bundle:** `PostHire-DU9UQUYi.js`  
**Status:** Production proof green — **do not freeze yet until product sign-off**; navigation soft-keep is ready for review.

## What shipped

- Soft-keep last committed board while the next week/day range loads (no blank wipe, no opacity flash, no full remount).
- Atomic replace only when the **latest** request matches the current target (`commitIfLatest`).
- Slower older responses are dropped.
- Week payload cache + ±1 adjacent prefetch; day view filters the week client-side.
- Chrome can lead (range label / target week); board paints committed range only.
- Scroll remember/restore on commit; filters / Day|Week / drawer selection preserved.
- Fixed `reloadFresh` to call `reload()` after cache invalidate (was recursive).

## Proof summary

| Check | Result |
| --- | --- |
| Bundle markers | `NAV_SOFT_KEEP_SMOKE_OK` |
| Pending soft-keep (rapid next burst) | `committed_week=2` held with **47** tiles while `target_week=9`; `pending=true`; updating rail on |
| Soft-keep blanks | `0` |
| Race settle | `committed_week == target_week` after burst |
| Delayed GETs exercised | `14` |
| IQ-12 recheck | see `verify/iq12-production-recheck.out` |

Key pending frame (from `after/nav-race-report.json`):

- Chrome label: Oct 4–10, 2026
- Board still Aug 16–22 week (47 tiles, height 1259.5)
- Then atomic settle to week 9 (empty week — correct content, not a load flash)

## Evidence paths

- Local: `ops/evidence/shifts-nav-soft-keep-prod-deploy-20260804T183237Z/`
- Remote: `/opt/wathefni/production-evidence/shifts-nav-soft-keep/20260804T183237Z/`
- Sequential screenshots: `after/01-*.png` … `after/10-seq-settled.png`
- Request-race report: `after/nav-race-report.json`
- Unit contracts: `tests/shifts-contracts.out` (+ `ShiftsBoardRangeContract.test.ts`)

## Rollback

```bash
/opt/wathefni/backups/production-pre-shifts-nav-soft-keep-20260804T183237Z/ROLLBACK.sh
```

Restores prior dashboard dist to `/opt/wathefni/dashboard-dist` and `/var/www/wathefni-dashboard`.

## Freeze gate

Shifts is **not frozen** by this deploy. Freeze only after product confirms the production transition feels smooth (soft-keep + atomic replace under rapid prev/next).
