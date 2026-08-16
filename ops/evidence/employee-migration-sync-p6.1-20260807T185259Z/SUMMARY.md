# Migration & Sync P6.1 — Live UI Refresh

| Field | Value |
|---|---|
| Stamp | `20260807T185259Z` |
| Verdict | **PASS** |
| Company | WATHEFNI (canary) |
| Design | `ops/EMPLOYEE_MIGRATION_SYNC_P6_1_LIVE_UI_REFRESH.md` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p6_1-20260807T185259Z/ROLLBACK.sh` |
| Dashboard | `PostHire-B84Q_9SB.js` |
| Backend | Unchanged (P1–P6 architecture frozen) |

## Approach

Event-driven invalidation on existing dashboard loaders — **no new realtime platform**:

- `CustomEvent` `wathefni:migration-sync-live` (same tab)
- `BroadcastChannel` `wathefni-migration-sync-live` (cross-tab profile / directory)
- Visibility one-shot + **30s soft poll** only while Connected / Needs Review / History / open profile are mounted (paused when tab hidden)
- Soft refresh keeps painted rows; skips dirty editors (name draft, edit modal, busy actions)
- Debounce + in-flight coalesce prevents request storms

## Proven

| Check | Result |
|---|---|
| Live bundle needles (event + BroadcastChannel + Connected/Review strings) | PASS |
| Source contract (emit, soft refresh, dirty guards, list+profile hooks) | PASS |
| Sync → connection/last_sync/runs/review list refresh sources | PASS |
| P6 leavers regression | PASS |
| P5.2 secret hardening regression | PASS |
| P1 foundation regression | PASS |

## Remaining gaps

- Owner live walk of Connected → Sync now / Needs Review open with scheduler tick not screenshot-stamped this session (API + bundle + wiring proven)
- Same-tab Migration Sync still replaces Employees/profile route; open-profile refresh is proven via soft poll + cross-tab BroadcastChannel
- **Stop.** Do not start further Migration & Sync phases. Do not start Auth Wave 2 Phase 6.
