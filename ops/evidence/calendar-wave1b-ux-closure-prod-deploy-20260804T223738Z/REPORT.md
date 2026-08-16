# Calendar Wave 1b UX Closure — production deploy

**Stamp:** `20260804T223738Z`  
**Calendar bundle:** `CalendarShell-NeJN1iBo.js`  
**Dashboard:** `dashboard-BmAfD70U.js` · **PostHire:** `PostHire-Dn-NJ9Mq.js`  
**Freeze:** `ops/CALENDAR_WAVE1B_UX_CLOSURE_FREEZE.md`

## Proof

| Check | Result |
| --- | --- |
| Unit / contract | passed (`tests/unit.out`) |
| Token colors | `bg-wf-accent-follow-soft` present; legacy hex absent |
| Category/status split | `data-calendar-category` |
| Health | 200 |

## Rollback

```bash
/opt/wathefni/backups/production-pre-calendar-wave1b-20260804T223738Z/ROLLBACK.sh
```

## Wave 2 projections

**GO** to plan flagged read-only emitters after Wave 1 preview review.  
**NO-GO** to ship new post-hire sources now.
