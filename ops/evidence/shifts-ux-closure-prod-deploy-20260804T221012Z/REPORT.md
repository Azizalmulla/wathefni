# Shifts UX closure — production deploy

**Stamp:** `20260804T221012Z`  
**Bundle:** `PostHire-5m8ecUXs.js`  
**Scope:** Dashboard UX only — IQ-12 + shifts backend authority unchanged. AnyDoc frozen track untouched.

## What shipped

- Single primary Schedule CTA in the header bar (no duplicate page H1 / CTA stack)
- Compact date chrome + filters as attached bars (not four competing control rows)
- Identity rail widened to **240px**; hours as badge; empty role/place dash removed
- Time labels no longer truncate mid-time; overnight shows Next day cue
- Empty / sparse weeks keep the 7-day grid; cell-level Schedule / + Add
- Drawer: technical badges removed; lighter scrim so board stays visible
- Unused Branch/Site/Team/Location tucked under **Advanced Organization** (kept visible when populated or options exist)
- Cell Schedule prefills employee name when opened from a roster row

## Production proof

| Check | Result |
| --- | --- |
| Unit tests | 27 passed (`tests/shifts-unit.out`) |
| Bundle markers | `UX_CLOSURE_MARKERS_OK` |
| Dist path | `WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist` |
| Health `:8010/health` | 200 |
| Live bundle | `PostHire-5m8ecUXs.js` |

Screenshots: skipped per product request — review live.

## Rollback

```bash
/opt/wathefni/backups/production-pre-shifts-ux-closure-20260804T221012Z/ROLLBACK.sh
```

Restores prior dashboard dist to `/opt/wathefni/dashboard-dist` and `/var/www/wathefni-dashboard`.

## Paths

- Local: `ops/evidence/shifts-ux-closure-prod-deploy-20260804T221012Z/`
- Remote: `/opt/wathefni/production-evidence/shifts-ux-closure/20260804T221012Z/`
- Backup: `/opt/wathefni/backups/production-pre-shifts-ux-closure-20260804T221012Z/`
