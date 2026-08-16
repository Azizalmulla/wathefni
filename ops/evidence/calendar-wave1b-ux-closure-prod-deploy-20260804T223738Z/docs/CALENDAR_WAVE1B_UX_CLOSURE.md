# Calendar Wave 1b — UX Closure + Dashboard Freshness

**Stamp:** `20260804T223738Z`  
**Freeze:** `ops/CALENDAR_WAVE1B_UX_CLOSURE_FREEZE.md`  
**Predecessor:** Rendering Stability Wave 2 · Calendar Wave 1 audit

## Calendar UX shipped

| Item | Result |
|---|---|
| Sticky selection / drawer | `selectedSnapshot` keeps drawer across range soft-keep |
| Scroll restore | capture before nav; restore when newest range settles |
| Latest request wins | TanStack query key + AbortSignal (unchanged) |
| Adjacent prefetch | Retained (~450ms) |
| Token colors | `wf-accent-follow/review/assess/paused` + `wf-frame` |
| Category ≠ status | Drawer shows Category · label and Status separately |
| Interview ownership | Unchanged — edit/cancel gated |
| New post-hire sources | **Not added** |

## Freshness matrix

| Page | Refresh behavior (before → after) | Auto new records? | Method | Interval | Insert vs banner |
|---|---|---|---|---|---|
| Overview | Manual / invalidate → + visibility poll on work queue + calendar strip | Yes (soft-keep replace) | RQ `refetchInterval` | 60s queue / 90s calendar overview | Auto-replace when ready |
| Jobs | Manual / mutation → + poll while page open | Yes | RQ | 120s | Auto-replace |
| Candidates | Manual / mutation / filters → + poll | Yes | RQ infinite | 90s | Auto-replace |
| Interviews | Soft-keep + sticky drawer → + poll | Yes | RQ | 60s | Auto-replace |
| Assessments | Soft-keep → + poll | Yes | RQ | 90s | Auto-replace |
| Needs Attention | Manual / remount → + soft poll | Yes | `useVisibilitySoftPoll` | 60s | Auto-replace |
| Onboarding | Manual / search / mutation | No (deferred) | — | — | Manual Refresh |
| Attendance | Manual / range / mutation | No (deferred) | — | — | Manual Refresh |
| Leave | Soft-keep + rematch | No (deferred) | — | — | Manual Refresh |
| Shifts | Soft-keep + week cache (frozen) | No (deferred) | — | — | Manual Refresh |
| Compliance | Manual + stale badge | No (deferred) | — | — | Manual Refresh |
| Alerts | Soft-keep reload → + soft poll (+ RQ notifications) | Yes | Soft poll + RQ | 60s | Auto-replace |
| Activity | Filter-driven load | No (deferred) | — | — | Filter / navigate |
| Calendar | Soft-keep + prefetch → + poll | Yes | RQ | 60s events | Auto-replace |

**Shared rules:** pause when tab hidden · no overlapping soft polls · soft-keep painted content · local mutations still invalidate immediately · manual Refresh remains fallback · no WebSockets/SSE · no backend authority change.

## Residuals

- Onboarding / Attendance / Leave / Shifts / Compliance / Activity still manual-or-mutation refresh (post-hire Query migration = later wave)
- Alerts HR-tasks half is soft-polled; shell Refresh still does not alone refresh tasks without page poll
- Calendar sticky selection does not auto-jump range to selected event
- “New updates available” banner not introduced — operational queues auto-replace under soft-keep

## Calendar Wave 2 projections

**GO** to plan read-only projection emitters (one module at a time, flagged) after product review of Wave 1 populated preview.  
**NO-GO** to deploy synthetic or new post-hire sources in production without that review.
