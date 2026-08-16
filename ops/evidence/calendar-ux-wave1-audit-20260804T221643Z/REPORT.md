# Calendar UX, Rendering & Populated Preview — Wave 1 audit

**Stamp:** `20260804T221643Z`  
**Mode:** Review only — **synthetic events NOT deployed**  
**Spec:** `ops/CALENDAR_UX_RENDERING_POPULATED_PREVIEW_WAVE1.md`

## Implementation truth

Calendar is a **mixed** recruiting-weighted surface:

- **Live on grid:** manual Calendar events + live timed interview projections
- **Interview owns** schedule mutations; Calendar owns manual CRUD
- **Not connected:** video/async interviews, follow-ups, employee start, onboarding, leave, compliance, payroll, shifts, training (leave/shifts = conflict checks only)
- **Not** unified HR time view yet

## Rendering findings

Soft-keep already present via React Query `keepPreviousData` + refresh strip + adjacent prefetch. Gaps vs Shifts: mild opacity flash, no scroll restore, local hex colors.

## Populated preview screenshots

| File | Coverage |
| --- | --- |
| `01-desktop-en-month.png` | Month, dense + empty days |
| `02-desktop-en-week.png` | Week overlaps |
| `03-desktop-en-day.png` | Day |
| `04-desktop-en-drawer.png` | Event drawer |
| `05-desktop-en-overlap-drawer.png` | Overlap + drawer |
| `06-desktop-ar-rtl-week.png` | Arabic RTL week |
| `07-desktop-ar-rtl-month.png` | Arabic RTL month |
| `08-mobile-en-week.png` | Mobile week |
| `09-mobile-ar-day.png` | Mobile Arabic day |
| `10-mobile-en-drawer.png` | Mobile drawer |
| `11-mobile-en-emptyish-day.png` | Sparse day |

Post-hire chips are striped **Preview** markers. Fixture: `preview/synthetic-events.json`.

## Proposed next step after review

Wave 1b UX-only soft-keep + token color migration — no new production sources.
