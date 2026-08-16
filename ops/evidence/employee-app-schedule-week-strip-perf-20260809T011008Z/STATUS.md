# Employee App — Schedule week strip rapid-tap performance

**Stamp:** `20260809T011008Z`  
**Verdict: PASS** (engineering + OTA). Physical rapid-tap stress not run in this session (no attached handset).

## Root cause

Rapid alternating taps were janky because each tap paid for **all** of:

1. **Stacked `Animated.spring`s** — new springs started without `stop()`, so intermediate selections kept animating
2. **Effect-driven animation** — a `useEffect([selectedDate])` (and a ready timer also keyed on `selectedDate`) fought the spring on every emit
3. **Full Schedule-root re-render** — `setSelectedDate` reconciled Upcoming + Recent + HR on every tap (`usePagedList` slices, cards, summary)
4. **Layout `setState` bump** — day `onLayout` called `bump()` and re-rendered the strip during selection
5. **Unbounded haptics** — `Haptics.selectionAsync()` on every tap under two-handed spam

Selection stayed client-side (no `/app/workday` refetch); the cost was JS reconciliation + animation queueing.

## What changed

| Fix | Detail |
| --- | --- |
| Interruptible capsule | `springRef.stop()` then replace; `useNativeDriver: true` |
| Latest-wins strip | Local `visualDate` moves capsule/cells immediately; parent date via `startTransition` |
| Isolate heavy lists | `memo(ScheduleTrailingSections)` — Upcoming/Recent/HR no longer re-render on date taps |
| Memo week/day cells | Inactive weeks keep `selectedDate={null}` so they skip reconcile |
| Measure without React state | Slot geometry in refs only |
| Haptic throttle | ≥90ms between selection haptics |
| Scroll only on week change | Same-week taps do not `scrollTo` |

Preserved: week paging, directional lock, data honesty, presence dots, Today jump, EN/AR/RTL, a11y.

## Deploy

| Field | Value |
| --- | --- |
| Channel | Canary OTA `3f83d757-7b30-4878-999a-f55e935d21cc` · runtime `0.1.0` · no native build |
| Rollback | `088982ab-67bd-4c23-ac50-acb6ae8841c4` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/3f83d757-7b30-4878-999a-f55e935d21cc |

## Smoke

| Check | Result |
| --- | --- |
| density + capability + tsc | PASS / GREEN |
| Physical rapid two-handed tap stress on iPhone | **Not run here** — pull OTA and spam 9→10→11→12→13 |

Expected after pull: capsule converges on the **latest** date; intermediates do not finish; Upcoming/Recent stay still while tapping.
