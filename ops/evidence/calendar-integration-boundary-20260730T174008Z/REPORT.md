# Calendar Integration Boundary — Production Report

**Stamp:** `20260730T174008Z`  
**Verdict:** **PASS**  
**Environment:** Production (`root@76.13.63.68`)  
**Prior cutover:** `calendar-sync-authority-20260730T140939Z` (authority move)  
**This stamp:** quiet **Not synced** + post–Ranking/Assessments re-verification

## Summary

Long-term integration authority remains outside Calendar. External sync / full console live only under **Settings → Platform Integrations**, dual-gated by `settings.manage` **and** `calendar.sync`. `hr_admin` does not receive automatic `calendar.sync` (owner default; others by explicit assignment). Event sync GET stays sanitized for ordinary Calendar readers. Calendar drawer may show only quiet **Synced** / **Not synced**. Provider integrations and operational proof preserved.

## Contract

| Surface | Authority |
|---|---|
| Calendar UI | No External sync, reconnect, legacy operator, or internal sync evidence |
| Settings → Platform Integrations | `settings.manage` ∧ `calendar.sync` |
| `calendar.sync` role default | `owner` only among HR roles; never auto via `hr_admin` / manager / recruiter |
| `GET …/events/{id}/sync` | Full bindings only with `calendar.sync`; readers get `detail: "status"`, empty `bindings`, `customer_status` only |
| Event drawer | Quiet Synced / Not synced from `customer_status` only |

## Live proof

| Check | Result |
|---|---|
| No External sync in Calendar assets | **PASS** |
| Platform Integrations in Settings | **PASS** |
| Quiet Synced + Not synced (+ AR) | **PASS** |
| Arabic type labels (`اجتماع`) | **PASS** |
| No stale “comes later” copy | **PASS** |
| `owner` has `calendar.sync` | **PASS** |
| `hr_admin` lacks `calendar.sync` | **PASS** |
| Sanitizer keys = `customer_status` only | **PASS** |
| Health | **PASS** `200` |

Evidence: `live-proof.json`.

## Files

### Backend (already live; verified)
- `wathefni-orchestrator/app.py` — `hr_admin` → `_CALENDAR_PERMS_OPS`; hardened `dashboard_calendar_event_sync_status`
- `wathefni-orchestrator/calendar_sync.py` — `public_event_sync_status()`
- `wathefni-orchestrator/smoke-test-calendar-sync-authority.py` — prefers deployed assets on prod
- `wathefni-orchestrator/smoke-test-calendar-c1.py` / `smoke-test-calendar-c5.py` / `smoke-test-multi-user-wave1-roles.py`

### Dashboard (this deploy)
- `apps/wathefni-dashboard/src/components/CalendarShell.tsx` — quiet Synced/Not synced; no console; AR labels; Mine only hidden on My
- `apps/wathefni-dashboard/src/components/PlatformIntegrationsPanel.tsx`
- `apps/wathefni-dashboard/src/pages/SettingsPage.tsx` — dual gate
- `apps/wathefni-dashboard/src/App.tsx` — calendar subtitle
- `apps/wathefni-dashboard/src/components/CalendarShell.test.tsx` / `PlatformIntegrationsPanel.test.tsx`

### Live assets
- `CalendarShell-Bkng-4pt.js`
- `SettingsPage-D_fp3gw_.js`
- `dashboard-CymfnsdK.js`

## Migration impact

**None.** No schema change. Role defaults + API response shape + UI placement only. Existing provider connections / sync bindings preserved.

## Rollback

```bash
/opt/wathefni/backups/production-pre-calendar-integration-boundary-20260730T174008Z/ROLLBACK.sh
```

Restores prior dashboard dist + smoke scripts (+ backed-up `app.py` / `calendar_sync.py` if needed).

Earlier authority rollback (if required):

```bash
/opt/wathefni/backups/production-pre-calendar-sync-authority-20260730T140939Z/ROLLBACK.sh
```

## Tests — PASS/FAIL

| Check | Result |
|---|---|
| `smoke-test-calendar-sync-authority.py` (prod) | **PASS** 39/39 |
| `smoke-test-calendar-c1.py` (prod) | **PASS** 45/45 |
| `smoke-test-multi-user-wave1-roles.py` (prod) | **PASS** |
| Vitest CalendarShell + PlatformIntegrations | **PASS** 10/10 |
| Live markers + sanitizer + role pins | **PASS** |
| Health | **PASS** `200` |

## Behavior

| Actor | Calendar | Settings → Platform Integrations | Event sync GET |
|---|---|---|---|
| Owner | Quiet Synced/Not synced only | Visible (both perms) | Full bindings + `customer_status` |
| HR Admin | Same calendar UX; no External sync | Hidden (lacks `calendar.sync`) | Sanitized status only |
| Ordinary `calendar.read` | Quiet status when useful | Hidden | `detail: status`, empty bindings |
