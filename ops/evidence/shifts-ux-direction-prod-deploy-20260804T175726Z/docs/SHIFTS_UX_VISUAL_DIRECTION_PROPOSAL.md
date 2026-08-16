# Shifts UX & Visual Direction Proposal

**Status:** IMPLEMENTATION — hierarchy approved; assignment-type governed; visual pending production evidence  
**Date:** 2026-08-04  
**Prerequisite:** Wave 3B roster architecture (`20260804T170817Z`) is live but not accepted as baseline  
**Authority:** Preserve Wave 1 scheduling authority and Wave 2 IQ-12 interaction contracts  
**Governed model:** `ops/SHIFTS_ASSIGNMENT_TYPE_GOVERNED_MODEL.md`

---

## 1. Blunt UX audit — busy non-technical HR

Wave 3B fixed the worst architectural mistake (spreadsheet cells that repeated identity). It did **not** make Shifts feel clean, modern, or fast to use.

### What a busy HR user experiences today

1. **Too much before the schedule.**  
   Live desktop stacks: page eyebrow + title + two subtitle lines + “latest data” pill + Schedule CTA + Schedule/Requests/Planning + Day/Week + date chrome + search/filters — then the board. On empty weeks the board is still near the fold bottom. Mobile is worse: status banner, subtitle, full-width CTA, tabs, date row, search, day strip, then agenda.

2. **Controls feel like four separate toolbars.**  
   Surface tabs, view/date, and filters do not read as one scheduling console. Hierarchy is unclear: what is primary navigation vs. what is board chrome vs. what is search?

3. **Primary action competes with itself.**  
   “Schedule a shift” appears in the page header and again in the empty board. Refresh sits beside the CTA on some breakpoints and beside the subtitle on others. Attention/status messaging adds another band.

4. **Identity still fails under density.**  
   The sticky rail is too narrow (~190px). Long Arabic/English names truncate. Role · site meta is tiny. Weekly hours are easy to miss. When many employees exist, the rail becomes a cramped label column rather than a person roster.

5. **Shift tiles are still product cards.**  
   Even after time-first work, tiles still carry location on nearly every cell (repeating the row’s site), status labels on healthy work, and overnight continuation copy (“Continues from Monday”, “22:00–”, “–06:00”). At density this becomes a wall of pastel chips, not a schedule.

6. **Overnight language is technical, not operational.**  
   HR needs “works tonight into tomorrow.” They do not need span markers or continuation fragments explained as engineering.

7. **The board still looks mechanical.**  
   Even without cell borders, equal columns + identical tile padding + legend strip read as an admin grid. References succeed with stronger day rhythm, clearer today wash, and fewer competing outlines.

8. **Requests and gaps are easy to miss.**  
   Requests live behind a peer tab. Empty lanes are blank rather than quiet coverage cues. Conflicts use yellow, but healthy olive still dominates so exceptions do not pop enough at a glance.

9. **Empty state over-explains.**  
   Large empty copy + second Schedule button wastes the hero. An empty week should still look like a week, with one obvious first action.

### Verdict

Roster lanes are the right **structure**. The live page is not yet a usable **product surface**. Do not freeze Wave 3B as Wathefni’s design baseline.

---

## 2. Proposed control hierarchy

### Goal in the first seconds

| Question | Answer location |
|---|---|
| Which week/day? | Compact schedule toolbar (range + Today + Day/Week) |
| Who is scheduled? | Sticky identity rail / mobile employee groups |
| When / what work? | Time-first tiles |
| Conflicts / gaps / requests? | Semantic tile states + compact Requests count on surface switch |
| Create / edit? | One primary CTA + click tile / empty lane |

### Desktop composition (top → bottom)

```
[ Page title only ]                    [ Schedule a shift ]
[ Schedule | Requests (n) | Planning ]   ← primary navigation only
[ Day · Week | ‹ Today › | 2–8 Aug ]     ← one schedule toolbar
[ Search employee · Team · Filters ]     ← one filter row
[ WEEKLY ROSTER BOARD — starts immediately ]
```

Rules:
- Remove duplicate subtitles / “understand this week…” instructional copy from the Shifts canvas.
- Move soft-update feedback to a 2px non-reflow rail on the board (IQ-12 preserved), not a large status pill above the fold.
- Keep Requests attention as a count on the Requests tab (and a quiet inline chip only when count > 0), not a full-width strip above the board.
- Primary CTA appears once in the page header (and as an inline empty-lane affordance on hover / empty week CTA inside the board scaffold — not a third floating duplicate).

### Mobile composition

```
[ Shifts ]
[ Schedule | Requests (n) | Planning ]
[ Day strip (7) + Today ]
[ Search · Filters ]
[ Selected day agenda grouped by employee ]
[ FAB: Schedule ]
```

Create/edit opens full-screen sheet. Filters open as a bottom sheet / popover.

---

## 3. Proposed shift-card information hierarchy

### Week tile (desktop)

1. **Time** — tabular, bold: `08:00–16:00`
2. **Role / shift label** — one line: `Front desk`
3. **Location/team** — only when it differs from the row’s primary site/team
4. **Exception label** — only when exceptional: `Conflict` / `Review` / `Cancelled`

Healthy scheduled tiles carry **no** status pill.

### Overnight

One operational phrase, not continuation engineering:

- `21:00–05:00 · Next day`

If the shift visually spans two day lanes, both fragments still select the same governed shift ID, but copy stays operational (no “Continues from Monday”).

### Overlap

Two compact side-by-side windows + yellow conflict treatment. No “split” banner.

### Identity rail (once per row)

- Initials avatar  
- Full name (no mid-name truncation at default desktop width; rail ≥ 220px)  
- Quiet meta: team · site  
- Weekly hours as secondary tabular meta  

Never repeat the employee name inside tiles.

### Day / mobile agenda

Group once by employee. Tiles follow the same time → role → optional place → exception order.

---

## 4. Reference-inspired palette (exact meanings)

Reuse Wathefni pre-hire tokens. No page-local hex invention. No coloring by employee and no random assignment.

### Normal-work rhythm driver: **assignment type**

References color ordinary calendar work by category (visit type / session type), not by person and not only by exception. For Wathefni Shifts, the equivalent durable dimension is **assignment type**, derived from the shift’s role / shift label (already on every governed shift).

| Assignment type | How it is recognized | Soft surface | Rail |
|---|---|---|---|
| Guest / front-of-house | Front desk, guest support/services, reception | warm yellow soft (`wf-accent-review-soft`) | yellow |
| Operations / floor | Opening, floor, operations, ops lead | olive soft (`wf-accent-priority-soft`) | olive |
| Night | Night supervisor / night team roles | muted blue soft (`wf-accent-follow-soft`) | blue |
| Event / specialty | Event support, training, specialty coverage | dusty pink soft (`wf-accent-assess-soft`) | pink |
| General / other | Unclassified role | neutral raised cream (`wf-surface`) | taupe/ink-muted |

Overnight wording remains operational (`21:00–05:00 · Next day`). Night assignment type already uses blue, so healthy overnight work stays branded without needing a second “overnight-only” fill for every spanning shift.

### Exception overlays — reserved semantics (win over category fill)

| State | Treatment | Why reserved |
|---|---|---|
| Conflict | Strong review yellow fill + `Conflict` label + ink rail | Attention / risk — never used as a silent healthy category |
| Reconciliation required | Strong assess pink fill + `Review` label | Sensitive decision |
| Cancelled | Taupe soft + `Cancelled` label | Inactive |
| Hard destructive confirm | Coral — confirm dialogs only | Not board decoration |

Rule: category color creates week rhythm for **healthy** work. Exception state **replaces** the category fill so risk never looks like a normal guest/event tile. Requests attention chrome may use review yellow because it is attention, not a schedule category.

### Shared token table

| Token | Approx | Meaning | Shifts use |
|---|---|---|---|
| `wf-canvas` / `wf-frame` | cream | App atmosphere | Page backdrop |
| `wf-surface-raised` | `#fffdf8` | Raised work surface | Board, drawer, neutral tiles |
| `wf-ink` | `#23211d` | Primary type / action / active | CTA, active tab, today marker |
| `wf-ink-muted` | `#756b5d` | Secondary type | Meta, filters |
| `wf-accent-priority` soft | olive | Operations assignment (healthy) | Ops / floor tiles |
| `wf-accent-review` soft | warm yellow | Guest assignment (healthy) **or** conflict when labeled | Guest tiles; conflict override |
| `wf-accent-assess` soft | dusty pink | Event/specialty (healthy) **or** recon when labeled | Event tiles; recon override |
| `wf-accent-follow` soft | muted blue | Night assignment / span information | Night tiles; Next day cue |
| `wf-accent-paused` soft | taupe | Inactive / cancelled | Cancelled tiles |
| `wf-accent-active` | coral | Hard risk (sparing) | Destructive confirm only |

Composition rule from references (translate, don’t copy):
- warm cream canvas + ink chrome  
- varied muted card fills across an ordinary week  
- today as ink marker + continuous quiet wash  
- status labels only for exceptions  
- denser useful content, less chrome padding  

---

## 5. Interaction & loading behavior (preserve IQ-12)

Unchanged contracts:
- soft-keep board content while refreshing  
- preserved filters and date range  
- sticky selected snapshot / drawer continuity  
- confirmation stays open until success  
- no duplicate submissions  
- clear success / error / cancellation feedback  
- governed org selectors + unmapped preservation  
- `expected_updated_at` / mutation payloads unchanged  

Presentation refinements (proposal only):
- `data-shifts-updating` = 2px progress rail; no whole-board opacity  
- history rows remain visible while refreshing (opacity only)  
- pending state local to initiating control  
- client-only status filter never triggers refetch  
- drawer = fixed end sheet (420px desktop / full-screen mobile); never resizes board  

---

## 6. Review artifacts

- Proposal: this file
- Interactive preview: `ops/previews/shifts-ux-direction/index.html`
- Screenshots: `ops/previews/shifts-ux-direction/screenshots/`
- Fixture covers: dense roster, multi-shift day, overnight · next day, conflict, reconciliation, cancelled, open requests, empty week, create/edit drawer, EN/AR, desktop/mobile

Query helpers:
- `?lang=ar` RTL Arabic
- `?drawer=create|edit`
- `?empty=1`
- `?surface=requests|planning`

**Production remains untouched until explicit approval.**
