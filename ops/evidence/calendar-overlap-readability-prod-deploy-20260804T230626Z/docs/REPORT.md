# Calendar overlap readability + drawer close

**Stamp:** `20260804T230626Z`  
**Bundle:** `CalendarShell-BEh0wbDt.js` · `dashboard-F43swlxg.js`  
**Live:** https://api.wathefni.ai/dashboard/ (Calendar)

## Fixes
- Cascade overlap layout (no sub-min-width columns; +N overflow)
- Title/time always ellipsis truncate (no letter-wrap)
- Drawer/composer portaled to `document.body`; larger close; backdrop close; body-lock only on mobile
- Leave/OOO titles no longer forced to “Busy” unless `busy_only`
- Removed hover translate jumps

## Rollback
`/opt/wathefni/backups/production-pre-calendar-overlap-readability-20260804T230626Z/ROLLBACK.sh`
