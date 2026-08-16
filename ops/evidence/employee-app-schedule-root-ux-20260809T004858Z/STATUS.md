# Employee App Phase 2 — Schedule root UX

**Stamp:** `20260809T004858Z`  
**Verdict: PASS**

## Goal

Refine Schedule root within current `/app/workday` contracts: Today dominant → Upcoming preview (5) → Recent attendance (~5) with a quieter 30-day Present/Late/Absent summary. No dump of the full fetched window. No fake multi-year history. Keep expected/recorded clarity and HR-owned honesty. Structural refinement only (not a Home redesign).

## What shipped

### Frontend (`apps/wathefni-employee-mobile`)

- `ScheduleView.tsx`
  - Root order: **Today → Upcoming → Recent → HR authority**
  - `UPCOMING_PREVIEW = 5` / `RECENT_PREVIEW = 5` via existing `usePagedList` + `ShowMoreButton` (`common.showMore`)
  - 30-day P/L/A summary retained, muted (`surfaceMuted`, smaller type), nested under Recent
  - Removed decorative `WathefniBloom` from the Schedule hero
  - Expected vs recorded, authority unavailable states, HR card unchanged in meaning
- `scripts/verify-density-hierarchy.py` — Schedule now required to page previews; bloom dump check updated

### Backend

- **No deploy.** `/app/workday` window remains `_WORKDAY_WINDOW_DAYS = 30`. Authority and projection unchanged.

## Deploy

| Field | Value |
| --- | --- |
| Channel | Canary OTA `8db2b731-8c39-40dc-beb0-9c92bba0addd` · runtime `0.1.0` · **no native build** |
| Rollback | prior canary `2c8c6f8f-9638-4099-8676-7f046bf56934` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/8db2b731-8c39-40dc-beb0-9c92bba0addd |

## Smoke (what could be tested without a physical handset)

| Check | Result |
| --- | --- |
| FE structure (order, previews, Show more, no bloom, no full dump, window note) | PASS — `fe-structure-smoke.txt` |
| Density hierarchy gate (94) | PASS |
| Capability foundation | GREEN |
| `tsc --noEmit` | PASS (empty) |
| Production workday projection contract (synthetic) | PASS — `workday-contract-smoke.txt` |
| Live Aziz/Talal workday shape (read-only) | PASS — Aziz recent=5 / upcoming=0 / window=30; Talal empty window; both authorities ready |
| Physical device visual (root scroll order, Show more affordance, quiet summary) | **Not run here** — no attached canary device in this session. OTA is live for Aziz/Talal pull. |

## Honesty notes

- Show more only pages within the already-fetched ~30-day window; copy stays `common.showMore`, not “full history”.
- Aziz currently has exactly 5 recent rows → Show more may be absent until the window has >5; Upcoming empty is a real fact (`noUpcoming`), not filler.
- EN/AR/RTL keys reused; no new copy keys required.

## Out of scope

- Leave / Payslips root phases
- New deeper history API
- Home composition changes
- Backend workday contract changes
