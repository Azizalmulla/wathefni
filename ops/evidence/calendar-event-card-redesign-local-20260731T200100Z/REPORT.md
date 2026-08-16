# Calendar event-card redesign — local qualification

**Stamp:** `20260731T200100Z`  
**Deployment:** **NO — local only**  
**Verdict:** **PASS**

## Duration diagnosis first

The event shown in the production screenshot was not stretched by CSS.

| Field | Live value |
|---|---|
| Event | `online meeting with aziz` |
| Event ID | `c3c3d8e7-dc0c-4fbd-9d57-8c91d1cc053b` |
| Start | `2026-08-01T06:00:00+00:00` = Aug 1, 09:00 Asia/Kuwait |
| End | `2026-08-02T07:00:00+00:00` = Aug 2, 10:00 Asia/Kuwait |
| Timezone | `Asia/Kuwait` |
| Duration | **1,500 minutes / 25 hours** |
| All day | `false` |
| Current status | `cancelled` |

The redesign preserves the stored interval and grid math. Cross-day time labels explicitly add `(+1d)` / `(+يوم)` so a 25-hour record cannot look like a one-hour event.

Evidence: `verify/live-event-detail.json`, `verify/live-duration-diagnosis.json`.

## Implemented

- Content begins at the top of every timed card.
- Compact rounded cards with semantic pastel mapping:
  - interview → blue
  - deadline / assessment → pink
  - meeting → green
  - tentative → yellow
  - personal / out-of-office / cancelled → neutral sand
- Timezone-aware start–end labels.
- Duration-driven progressive disclosure:
  - short `<75m`: title + time
  - medium `75–149m`: title + time + type/status
  - long `≥150m`: context + channel/location + participants + Join where available
- Candidate/job context from governed event metadata/guest data.
- Teams / Meet / Zoom / online, office/location, and phone indicators.
- Participant initials/count where width permits.
- Join opens the existing meeting URL without opening the detail drawer.
- Clicking / keyboard-activating the rest of the card still opens the existing detail surface.
- Greedy overlap lanes; actual start/end/top/height are unchanged.
- Narrow overlapping cards automatically disclose less.
- Stronger day grouping, softer half-hour/hour dividers, readable localized time labels.
- Filters, controls, and grid visually grouped more tightly.
- Scope switcher, queries, permissions, drawer, create/edit, and event authority unchanged.

## Qualification

| Gate | Result |
|---|---|
| Live start/end/timezone verified before CSS work | **PASS** |
| Short event (30m / 28px) | **PASS** |
| Medium event (90m / 72px) | **PASS** |
| Long event (180m / 144px) | **PASS** |
| Overlapping events | **PASS** (`1/2`, `2/2` lanes) |
| Empty week | **PASS** |
| Teams event + Join | **PASS** |
| Candidate/job context + participants | **PASS** |
| EN desktop | **PASS** |
| AR + RTL + Arabic Join | **PASS** |
| Mobile day/agenda | **PASS** |
| Scope switcher preserved | **PASS** |
| Existing drawer behavior | **PASS** |
| Calendar/Overview tests | **PASS** — 13/13 |
| TypeScript production build | **PASS** |
| IDE lint diagnostics | **PASS** |

## Screenshots

Same fixture data was routed through production UI and then the local redesign for an apples-to-apples comparison.

- Before: `screenshots/before/calendar-before-same-fixtures.png`
- After EN desktop: `screenshots/after/calendar-after-en-desktop.png`
- After AR/RTL: `screenshots/after/calendar-after-ar-rtl.png`
- After mobile: `screenshots/after/calendar-after-mobile.png`
- After empty week: `screenshots/after/calendar-after-empty-week.png`

## Local artifact

- Chunk: `CalendarShell-C7IuIh4S.js`
- SHA-256: `b013f7434f69103f1453a15ef562022a6cc28c092cbf783b0da7dd9cc41e0137`

## Evidence path

`/Users/azizalmulla/Desktop/claw/ops/evidence/calendar-event-card-redesign-local-20260731T200100Z`
