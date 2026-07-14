# HR-1 — Safe Rollback

Rollback is **staging-first**. HR-1 must not be promoted to production until reviewed.

## What HR-1 adds

- Module: `operator_mobile.py`
- Routes: `/dashboard/mobile/auth/*`, `/dashboard/mobile/me`
- Tables: `dashboard_operator_mobile_sessions`, `dashboard_operator_mobile_login_attempts`
- Wiring in `app.py` (import, schema ensure, route register, disable/lifecycle revoke hooks)
- Deploy ship list includes `operator_mobile.py`

## Soft disable (preferred)

1. Stop routing any Wathefni HR client to `/dashboard/mobile/*` (no client ships in HR-1).
2. Optionally leave tables in place; unused sessions expire/revoke naturally.
3. Browser `/dashboard/auth/*` and Employee `/app/*` remain untouched.

## Hard rollback on staging

```bash
# From a known pre-HR-1 staging artifact / git SHA:
cd /path/to/claw/wathefni-orchestrator
# Restore prior app.py without operator_mobile registration, or:
git checkout <pre-hr1-sha> -- app.py operator_mobile.py ops/deploy.sh

# Redeploy staging only
ops/deploy.sh staging
```

Optional table cleanup (staging harness companies only — do **not** run broad production drops):

```sql
-- Staging throwaway only
DELETE FROM dashboard_operator_mobile_sessions WHERE company_code IN ('HR1MOB','HR1OTH');
-- Full drop only if explicitly approved for staging:
-- DROP TABLE IF EXISTS dashboard_operator_mobile_login_attempts;
-- DROP TABLE IF EXISTS dashboard_operator_mobile_sessions;
```

## Do not

- Roll back HR-0A authority remediations as part of HR-1 undo
- Touch production company configuration
- Disable Employee App contracts
- Re-enable legacy shared-token authority

## Verify after rollback

- `GET /dashboard/mobile/me` → 404 (route gone) or service without module
- `POST /dashboard/auth/login` still works
- Employee App `/app/*` unchanged
- Staging smoke suite green
