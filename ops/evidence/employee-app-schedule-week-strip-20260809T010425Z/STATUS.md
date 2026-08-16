# Employee App — Schedule week / day selector

**Stamp:** `20260809T010425Z`  
**Verdict: PASS** (engineering + OTA). Physical swipe/tap feel not exercised on a handset in this session.

## Contract limitation (objective)

`/app/workday` does **not** support arbitrary day detail fetches. One payload, Kuwait today-centred:

| Slice | What it contains |
| --- | --- |
| `today.entries` | Expected **and** recorded, paired for **today only** |
| `upcoming` | Shifts from **tomorrow → today+30** (no attendance) |
| `recent` | Attendance for **today−30 → yesterday** (no past shift roster) |
| Outside window | **No facts** |

So true day navigation is **client-side over the fetched window only**:

- **Today** → full expected + recorded (unchanged)
- **Future in window** → expected shift(s) only; never invent “not recorded yet”
- **Past in window** → attendance row(s); expected times only when the attendance record itself carries `scheduled_start` / `scheduled_end`
- **Outside window** → explicit `schedule.dayOutsideWindow` (no empty-as-fact)

No backend change. No `?date=` API. No fabricated multi-year history.

## What shipped

- `ScheduleWeekStrip` — cream, no card; black capsule with spring; week paging + momentum; `directionalLockEnabled`; EN Sun-start / AR Sat-start + RTL day row; presence dots from canonical dates only; today mark when unselected; 44pt cells; Dynamic Type caps; selection haptics
- Selected-day panel updates from real payload via `resolveSelectedDay`
- Non-today section title = formatted date (not “Today”); quiet **Today** jump control
- Phase 2 root kept: **week strip → selected day → Upcoming(5) → Recent(5)+quiet P/L/A → HR**

## Deploy

| Field | Value |
| --- | --- |
| Channel | Canary OTA `088982ab-67bd-4c23-ac50-acb6ae8841c4` · runtime `0.1.0` · **no native build** |
| Rollback | `8db2b731-8c39-40dc-beb0-9c92bba0addd` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/088982ab-67bd-4c23-ac50-acb6ae8841c4 |

## Smoke

| Check | Result |
| --- | --- |
| Day model (today / future / past / outside / presence) | PASS — `day-model-smoke.txt` |
| Density + capability gates · EN/AR keys · tsc | PASS / GREEN |
| Physical iPhone swipe vs vertical scroll / capsule motion | **Not run** — no attached canary device |

## Device follow-through (canary)

After OTA pull: tap days, swipe weeks across month boundary, scroll Schedule vertically without fighting the strip, confirm capsule motion and honest empty/outside copy.
