# Organization Wave 1 — production visual deploy

Stamp: `20260804T053014Z`

## Boundary decisions
1. **View vs manage:** Live GET `/employee-org/units` previously required `employees.manage` only. Corrected to allow `employees.read` **or** `employees.manage` for structure viewing. Mutations (upsert, reconcile, Advanced admin) remain `employees.manage`.
2. **Hierarchy language:** Column is **Parent unit** / unit hierarchy — not employee–manager reporting lines.

## Deployed
- Dashboard dist → `/var/www/wathefni-dashboard`
- `app.py` units list permission gate → `/opt/wathefni/orchestrator/app.py`

## Rollback
```bash
bash /opt/wathefni/backups/production-pre-organization-wave1-20260804T053014Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-organization-wave1-20260804T053014Z
```

## Advanced
Unfrozen; authority unchanged (lifecycle / remediation / migration / ESS gates unchanged).
