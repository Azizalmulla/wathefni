# Employee App Phase 3 — Leave root UX

**Stamp:** `20260809T011317Z`  
**Verdict: PASS**

## Goal

Refine Leave around the real employee job within the existing `/app/leave` contract: balances (only when canonical) → Request leave → Current → Recent history, with Show more inside the fetched ~50 window. No year/status filters. No broad visual redesign.

## Contract honesty

| Fact | Behavior |
| --- | --- |
| `balances_enabled` + usable `available`/`current_balance` | Show Balance section + subtitle that mentions balances |
| balances off / empty / no usable number | Hide Balance section; subtitle does **not** promise balances |
| entitlement / accrual fields | Never invented or displayed unless already used by `balanceForLeaveType` (available/current only) |
| Cancel | Unchanged: capability `leave.cancel` + status `requested`\|`approved` (matches `/app/leave/{id}/cancel`) |
| API window | Server `LIMIT 50`; Show more pages Current/History separately (8); note when count ≥ 50 |

## What shipped

- `leaveRequests.ts` — `partitionLeaveRequests` (current vs terminal history); `LEAVE_CANCELLABLE_STATUSES`
- `LeaveView` — order: balances? → Request → Current → Recent history → empty/window note
- Current ordered: needs-attention (`requested`) first, then live rows by start date
- History: cancelled / rejected / completed (and aliases); no cancel affordance
- EN/AR: `leave.subtitleWithBalances`, `leave.subtitleRequestsOnly`, `leave.currentRequests`, `leave.history`, `leave.listWindowNote`
- Density gates updated for balances gate + partition + cancel constants

## Deploy

| Field | Value |
| --- | --- |
| Channel | Canary OTA `f151fbb5-f174-47bc-9c78-4f45c1af5c2f` · runtime `0.1.0` · **no native build** |
| Rollback | `3f83d757-7b30-4878-999a-f55e935d21cc` |
| Backend | No deploy |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/f151fbb5-f174-47bc-9c78-4f45c1af5c2f |

## Smoke

| Check | Result |
| --- | --- |
| Partition + cancellable status unit | PASS — `partition-smoke.txt` |
| Density (96) + capability GREEN + tsc | PASS |
| Live Aziz | `balances_enabled=False`, 2 requests → 1 current / 1 history — PASS |
| Live Talal | empty leave — PASS |

## Out of scope

- Year / status history filters
- Deeper leave history API
- Leave request form redesign
- Home composition changes
