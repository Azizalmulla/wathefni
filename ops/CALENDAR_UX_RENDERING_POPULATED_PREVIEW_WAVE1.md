# Calendar UX, Rendering & Populated Preview — Wave 1

**Mode:** Review only — **do not deploy** synthetic events or new post-hiring sources  
**Audit stamp:** `20260804T221643Z`  
**Evidence:** `ops/evidence/calendar-ux-wave1-audit-20260804T221643Z/`  
**Shifts predecessor (frozen):** `ops/SHIFTS_UX_PERMANENT_FREEZE.md` · `20260804T221537Z`

## Implementation truth (confirmed)

Calendar today is a **mixed recruiting-weighted scheduling surface**, not a unified HR time view.

| Source | On grid today? | Mutation owner | Calendar role |
|---|---|---|---|
| Manual events (`meeting`, `personal_block`, `deadline`, `out_of_office`, `other`) | Yes | **Calendar** | Create / edit / cancel with `calendar.manage` |
| Live timed interviews | Yes (projected) | **Interviews** | Display + RSVP/detail; schedule authority blocked |
| Async / video interviews | No (explicit skip) | Interviews | Not timed calendar events |
| Candidate follow-ups / assessment / offer deadlines | ACL names only | — | **No emitters** |
| Employee start / onboarding / leave / compliance / payroll / shifts / training | No | Specialist modules | Leave/shifts conflict **checks only** |
| Google / Microsoft sync | Mirror only | Calendar sync (`calendar.sync`, owner) | Not an event source |

**Verdict:** not recruiting-only (manual calendar exists), not display-only (Calendar mutates manual events), not unified HR time plane. **Mixed.**

Long-term boundary: Calendar = Wathefni’s **unified HR time view / projection spine**; each specialist module keeps **workflow ownership** (create/reschedule/cancel of linked work).

## Rendering findings (live `CalendarShell`)

Already close to Shifts soft-keep:

- `keepPreviousData` while day/week/month changes
- Quiet top “Refreshing…” strip when `isFetching && data`
- Adjacent period prefetch (~450ms)
- Filters / scope / selection preserved across range changes
- No full-grid remount key

Gaps vs Shifts bar:

- Mild opacity flash (`opacity-95`)
- No explicit scroll restore
- Selection can remain if event leaves the new range
- Category colors are **local hex**, not shared `wf-accent-*` tokens

## Proposed category / color contract

**Category ≠ status.** Status overlays (`cancelled`, `tentative`, `confirmed`, `completed`) stay separate.

| Category | Live today? | Proposed token family | Notes |
|---|---|---|---|
| Interview | Yes | `wf-accent-follow` (blue) | Keep |
| Video interview | Preview | `wf-accent-follow-soft` | Distinct from live timed |
| Candidate follow-up | Preview | `wf-accent-review` | Align recruiting yellow |
| Meeting / training | Manual / preview | `wf-frame` cream | Default work block |
| Employee start | Preview | `wf-accent-priority` | Post-hire milestone |
| Onboarding deadline | Preview | `wf-accent-assess` | Deadline family |
| Approved leave / OOO | Preview / OOO live | stone | Busy / absence |
| Compliance expiry | Preview | `wf-accent-review` | Deadline cue |
| Payroll cutoff | Preview | ink-soft | Operational marker |
| Cancelled (status) | Yes | muted stone | Wins over category |
| Tentative (status) | Yes | pink | Only when category doesn’t own fill |

## Production-safe implementation plan (next waves — after review)

1. **Wave 1b (UX only, no new sources):** Align Calendar soft-keep to Shifts bar (no opacity flash, quieter progress, scroll restore); migrate `eventSurfaceClass` hex → design tokens; EN/AR labels for categories; drawer polish. **No synthetic deploy.**
2. **Wave 2 (projection emitters, one source at a time):** Start with read-only projections that already have authority modules (e.g. approved leave windows, compliance expiries) behind flags; Calendar remains display for linked rows; mutations stay in Leave / Compliance / etc.
3. **Wave 3:** Candidate follow-up / onboarding deadline emitters if product prioritizes hiring continuum.
4. **Never:** Fake production integrations; invent interview schedule from Calendar; weaken `calendar.sync` owner-only; bypass interview authority fields.

Preserve: calendar-sync permissions, interview scheduling authority, specialist-module mutations, audit, backend contracts.

## Populated preview

Deterministic synthetic fixture + HTML preview (striped **Preview** chips for post-hire). Screenshots under `screenshots/`. **Deployed (WATHEFNI canary):** stamp `20260804T224543Z` · flag `WATHEFNI_CALENDAR_POPULATED_PREVIEW` · evidence `ops/evidence/calendar-populated-preview-prod-deploy-20260804T224543Z/`.
Still review-only: no real module records / no production emitters.

## Wave 1c visual closure

Stamp `20260804T225623Z` — see `ops/CALENDAR_WAVE1C_VISUAL_CLOSURE.md`. **NO-GO** on Wave 2 projections until approved.
