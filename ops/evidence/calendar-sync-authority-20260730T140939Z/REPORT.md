# Calendar Sync Authority Move — Production Report

**Stamp:** `20260730T140939Z`  
**Verdict:** **PASS**  
**Environment:** Production (`root@76.13.63.68`)

## Summary

Long-term integration authority moved out of Calendar into **Settings → Platform Integrations**. `calendar.sync` is revoked from `hr_admin` and remains owner-default (or explicit assignment only). Event sync GET is hardened for ordinary `calendar.read` callers.

## Files changed

### Backend
- `wathefni-orchestrator/app.py` — `hr_admin` uses `_CALENDAR_PERMS_OPS` (no `calendar.sync`); hardened `GET /dashboard/calendar/events/{event_id}/sync`
- `wathefni-orchestrator/calendar_sync.py` — `public_event_sync_status()` customer-facing sanitizer
- `wathefni-orchestrator/smoke-test-calendar-sync-authority.py` — new permission/API/UI placement smoke
- `wathefni-orchestrator/smoke-test-calendar-c1.py` — pin `hr_admin` has no `calendar.sync`
- `wathefni-orchestrator/smoke-test-calendar-c5.py` — UI markers point at Settings panel
- `wathefni-orchestrator/smoke-test-multi-user-wave1-roles.py` — pin HR Admin lacks `calendar.sync`

### Dashboard
- `apps/wathefni-dashboard/src/components/PlatformIntegrationsPanel.tsx` — **new** (moved console)
- `apps/wathefni-dashboard/src/components/CalendarShell.tsx` — stripped External sync / console / internal sync evidence; quiet Synced; AR labels; hide Mine only on My; labeled event types
- `apps/wathefni-dashboard/src/pages/SettingsPage.tsx` — Platform Integrations gated by `settings.manage` **and** `calendar.sync`
- `apps/wathefni-dashboard/src/App.tsx` — removed `canSync` prop; fixed stale week/month copy
- `apps/wathefni-dashboard/src/lib/api.ts` — sync response types (`detail`, `customer_status`)
- `apps/wathefni-dashboard/src/components/CalendarShell.test.tsx` — new
- `apps/wathefni-dashboard/src/components/PlatformIntegrationsPanel.test.tsx` — new (owner vs hr_admin)

### Live assets
- `CalendarShell-2449y5UN.js`
- `SettingsPage-Cj1Jh3Wk.js`
- `dashboard-B-yUXbUt.js`

## Migration impact

**None.** No schema migration. Role defaults and API response shape only.

- Existing provider integrations / sync bindings / operational proof preserved.
- `hr_admin` loses `calendar.sync` on next permission resolution (role defaults; no DB grant migration).
- Non-sync callers of event sync GET receive `detail: "status"`, empty `bindings`, and `customer_status` only.

## Rollback

```bash
/opt/wathefni/backups/production-pre-calendar-sync-authority-20260730T140939Z/ROLLBACK.sh
```

Restores:
- `/opt/wathefni/orchestrator/app.py`
- `/opt/wathefni/orchestrator/calendar_sync.py`
- `/var/www/wathefni-dashboard/` from pre-deploy snapshot

## Tests — PASS/FAIL

| Check | Result |
|---|---|
| `smoke-test-calendar-sync-authority.py` (prod) | **PASS** 38/38 |
| `smoke-test-calendar-c1.py` (prod) | **PASS** 45/45 |
| `smoke-test-multi-user-wave1-roles.py` (prod) | **PASS** |
| Vitest CalendarShell + PlatformIntegrations (local) | **PASS** 9/9 |
| Live markers (no External sync; Platform Integrations present; Synced; no “comes later”) | **PASS** |
| Health after restart | **PASS** `200` |
| `owner` has `calendar.sync` | **PASS** |
| `hr_admin` lacks `calendar.sync` | **PASS** |

## Behavior after cutover

| Actor | Calendar | Settings → Platform Integrations | Event sync GET |
|---|---|---|---|
| Owner | No setup/reconnect/legacy; quiet Synced only | Visible (has both perms) | Full bindings + `customer_status` |
| HR Admin | Same calendar UX; no External sync | Hidden (has `settings.manage`, lacks `calendar.sync`) | Sanitized status only |
| Ordinary calendar.read | Quiet Synced when useful | Hidden | Sanitized status only; empty bindings |
