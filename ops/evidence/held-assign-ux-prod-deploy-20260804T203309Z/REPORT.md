# Held CV Assign Job UX — production deploy

**Stamp:** `20260804T203309Z`  
**Bundle:** `CandidatesPage-D_7wPUac.js`  
**Scope:** Dashboard UX only — intake / eligibility / duplicate / permission / audit / admit authority unchanged.

## Deployed behavior

- Per-row **Assign job** → governed selector → **Assign and admit** for that `app_key` only
- Confirm disabled until a job is chosen (row + bulk)
- Checkboxes = explicit bulk only; bulk toolbar only after selection
- Bulk copy: `N selected — all selected candidates will receive the same job.`
- No whole-group fallback when nothing is checked

## Production proof

| Check | Result |
| --- | --- |
| Bundle smoke | `HELD_ASSIGN_UX_SMOKE_OK` |
| Single Assign job payload | `app_keys: ["imp-wathefni-3673b2f6eeab34c8-WATHEFNI-IMPORT"]` only |
| Unchecked sibling | `imp-wathefni-4115005c9dcdfc37-…` never in payload |
| Bulk toolbar before select | absent |
| Bulk copy | `1 selected — all selected candidates will receive the same job.` |
| Confirm without job | disabled |
| Preview | ok |
| Whole-group fallback | absent after clearing selection |
| Held rows preserved (dry-run intercept) | `needs_role` count still **2** |

Screenshots: `after/01-held-card.png` … `after/07-cleared-selection.png`  
Request report: `after/held-assign-ux-report.json`  
Unit tests: `tests/held-assign-unit.out` (6 passed)

## Rollback

```bash
/opt/wathefni/backups/production-pre-held-assign-ux-20260804T203309Z/ROLLBACK.sh
```

Restores prior dashboard dist to `/opt/wathefni/dashboard-dist` and `/var/www/wathefni-dashboard`.

## Paths

- Local: `ops/evidence/held-assign-ux-prod-deploy-20260804T203309Z/`
- Remote: `/opt/wathefni/production-evidence/held-assign-ux/20260804T203309Z/`
