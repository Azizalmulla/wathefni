# Calendar Wave 1c — Final Visual Closure (WATHEFNI canary)

**Stamp:** `20260804T225623Z`  
**Live URL:** https://api.wathefni.ai/dashboard/ (Calendar)  
**Flag (unchanged):** `WATHEFNI_CALENDAR_POPULATED_PREVIEW`  
**Calendar bundle:** `CalendarShell-CAwwaJGh.js`  
**Dashboard:** `dashboard-c-j4Ujpu.js`

## Proof

| Check | Result |
| --- | --- |
| Vitest Wave 1b + 1c + CalendarShell | 19/19 pass |
| Preview smoke | pass (titles omit Preview prefix; flags disclose) |
| Live inject sample | Interview · Omar… / Payroll cutoff / Video interview · Lina |
| Bundle markers | wave1c + overlay + tokens; no Wathefni Calendar h1; no grid push |
| Health | ok |
| Screenshots | `screenshots/` (EN/AR, week/month/day, drawer, mobile sheet) |

## Screenshots

- `01-desktop-en-week-dense.png`
- `02-desktop-en-month.png`
- `03-desktop-en-day-sparse.png`
- `04-desktop-en-overlay-drawer.png`
- `05-desktop-ar-rtl-week.png`
- `06-desktop-ar-rtl-month.png`
- `07-desktop-ar-rtl-drawer.png`
- `08-mobile-en-day.png`
- `09-mobile-en-bottom-sheet.png`
- `10-mobile-ar-day.png`

Fixture: `preview/wave1c-visual-fixture.html` (matches Wave 1c chrome; live canary uses same contracts).

## Rollback

```bash
/opt/wathefni/backups/production-pre-calendar-wave1c-20260804T225623Z/ROLLBACK.sh
```

Preview kill-switch remains:

```bash
# WATHEFNI_CALENDAR_POPULATED_PREVIEW=off then restart
```

## Wave 2

**NO-GO** until Wave 1c visual closure is approved. No new event sources or authority changes in this stamp.
