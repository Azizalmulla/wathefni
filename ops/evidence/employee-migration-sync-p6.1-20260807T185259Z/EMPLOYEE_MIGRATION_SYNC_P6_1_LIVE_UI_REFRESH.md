# Migration & Sync P6.1 — Live UI Refresh

Polish pass on frozen P1–P6. **No** backend/sync architecture change.  
**Do not** start further Migration & Sync phases or Auth Wave 2 Phase 6.

## Goal

After a Connected Systems sync (or relevant migration data change), HR sees updated
status / Needs Review / employees / open profile / history **without** a manual
browser reload.

## Approach

Reuse existing dashboard data patterns (`useModuleData` soft reload + Migration Sync
local loaders). No new realtime platform.

| Mechanism | Role |
|---|---|
| `CustomEvent` `wathefni:migration-sync-live` | Same-tab fanout after sync / review / lifecycle / import |
| `BroadcastChannel` `wathefni-migration-sync-live` | Cross-tab (Migration Sync in one tab → open profile in another) |
| Visibility one-shot | Soft refresh when tab becomes visible again |
| Soft poll 30s while Connected / Needs Review / History / open profile mounted | Catches scheduler-driven syncs; paused when tab hidden |

Source: `apps/wathefni-dashboard/src/lib/migrationSyncLive.ts`

## Guards

- Soft refresh keeps painted rows (no full-page blank / filter reset)
- Skip while local editors dirty (Add-connection name draft, edit modal, approver pick, busy actions)
- Debounce + in-flight coalesce → no request/re-render storm
- Import preview drafts are not clobbered by soft poll (Import section does not subscribe)

## Surfaces refreshed

- Connected Systems status / last sync / counts / sync history
- Needs Review rows + nav badge (import + lifecycle)
- History list + open batch detail
- Employees directory (when mounted)
- Open employee profile (same or other tab)

## Prove

See stamp under `ops/evidence/employee-migration-sync-p6.1-*`.
