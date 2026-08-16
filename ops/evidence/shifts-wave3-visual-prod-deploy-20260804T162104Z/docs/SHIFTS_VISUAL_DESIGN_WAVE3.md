# Shifts Visual Design Wave 3 — Shared Post-Hiring Visual Baseline

**Status:** SHIPPED — stamp `20260804T162104Z`  
**Prerequisite IQ-12:** `20260804T155956Z` (preserved)  
**Evidence:** `ops/evidence/shifts-wave3-visual-prod-deploy-20260804T162104Z/`  
**Live:** `/opt/wathefni/dashboard-dist/assets/PostHire-Cjhqi0Um.js`  
**Authority:** NO reopen of scheduling / mutations / permissions / backend

---

## 1. Visual audit — live Shifts (post IQ-12)


### What works
- Cream/ink foundation matches Wathefni shell
- Soft-keep loading, sticky drawer, confirm integrity already green
- Shift blocks already use *some* pastel fills for conflict / recon / overnight
- Surface tabs use ink active pills (good inverted-active pattern)

### What’s flat / weak
- **Board hero is quiet cream-on-cream** — `#fbf7ee` frame + `#e9e4d9` default blocks blend into canvas
- **Heavy borders everywhere** — `#ded3c1` / `#e8dfd0` on board, filters, request cards, planning panels
- **Date headers** use gold wash for “today” instead of strong ink inverted focus (reference + pre-hire prefer ink)
- **Filters** are plain white bordered inputs — not compact chrome
- **Empty state** is dashed box + text only — no designed rhythm
- **Requests/Planning** compete visually with Schedule (same bordered white cards)
- **Typography hierarchy** inside blocks: status chip competes with name; meta not quiet enough
- **Mobile day agenda** inherits same flat cream; density OK but cards lack semantic punch
- **RTL** works structurally but empty/hero composition isn’t intentionally designed for Arabic (mirroring only)

### Comprehension gaps
- Scheduled vs cancelled vs conflict don’t map to the **pre-hire token names** HR already learned on Overview/Jobs/Interviews
- Overnight blue is ad-hoc hex (`#b9cde8`) instead of `wf-accent-follow`
- Conflict yellow is ad-hoc (`#f3d85f`) instead of `wf-accent-review`

---

## 2. Proposed shared palette (token names + meaning)

Reuse and **extend documentation** of existing pre-hire `@theme` tokens in `index.css` — do **not** invent page-local hex.

| Token | Hex (existing) | Meaning (product-wide) | Post-hire / Shifts use |
|---|---|---|---|
| `wf-canvas` | `#eee8da` | App canvas | Page background (shell) |
| `wf-surface` / `wf-surface-raised` | `#fffaf0` / `#fffdf8` | Raised panels | Board frame, aside, calm lists |
| `wf-ink` | `#23211d` | Primary type + primary actions + inverted active | Day/Week active, Today header, Schedule CTA |
| `wf-ink-muted` | `#756b5d` | Secondary type | Meta, filters labels |
| `wf-accent-priority` (+ soft/ink) | olive `#a9ba7d` | Healthy / complete / on-track | **Scheduled** shift blocks |
| `wf-accent-review` (+ soft/ink) | soft yellow `#f1d96f` | Attention / warning | **Conflicted** shifts; attention strip |
| `wf-accent-assess` (+ soft/ink) | dusty pink `#e8acd0` | Decision / sensitive review | **Reconciliation required** |
| `wf-accent-follow` (+ soft/ink) | muted blue `#b4c9e5` | Schedule / span / follow-up | **Overnight / spanning** markers |
| `wf-accent-paused` (+ soft/ink) | taupe `#c4b49a` | Inactive / cancelled | **Cancelled** shifts |
| `wf-accent-active` (+ soft/ink) | coral `#e2574c` | Hard risk (sparing) | Destructive confirm only — not board decoration |
| `accent` / gold | `#c89445` | Brand hairline only | Selected ring (sparing) — not “today” fill |

**Rule:** same color → same meaning across pre-hire and post-hire. No random page colors.

### Aliases for post-hire docs (same CSS values)
- `ph-state-scheduled` → priority  
- `ph-state-conflict` → review  
- `ph-state-recon` → assess  
- `ph-state-overnight` → follow  
- `ph-state-cancelled` → paused  

---

## 3. Alignment with pre-hiring

| Pre-hire surface | Accent meaning | Shifts Wave 3 |
|---|---|---|
| Interviews summary (follow/review/priority) | schedule / attention / complete | overnight / conflict / scheduled |
| Jobs status tiles | priority / review / paused / follow | same token families on shift states |
| Assessments assess-soft | review pipeline | reconciliation |
| Overview attention yellow | needs decision | conflict + request attention strip |

CalendarShell still uses legacy hex for events — **out of scope to rewrite**, but Shifts becomes the post-hire reference that Calendar can adopt later.

---

## 4. Where each accent appears in Shifts

| Accent | Appearances |
|---|---|
| Priority (olive) | Default scheduled blocks; optional empty-state wash |
| Review (yellow) | Conflicted blocks; attention strip when requests > 0 |
| Assess (pink) | Reconciliation blocks + recon request cards |
| Follow (blue) | Overnight / ends-next-day blocks + span hint |
| Paused (taupe) | Cancelled blocks |
| Ink | Surface tabs active, Day/Week active, **today column header pill**, primary Schedule button |
| Surface raised | Board hero container (soft, low border), aside |
| Quiet cream | Requests / Planning cards (calmer than Schedule) |

---

## 5. Accessibility & contrast risks

| Risk | Mitigation |
|---|---|
| Soft yellow on cream — weak for color-blind | Pair with status chip text + `text-wf-accent-*-ink` (never yellow text on yellow) |
| Pink recon vs olive scheduled — ok for deuteranopia if labels remain | Keep status label chip |
| Blue overnight vs olive scheduled | Distinct hue families already in pre-hire contract |
| Selected ring gold on pastel | Use ink ring or gold at ≥55% opacity + keep selected id sticky |
| Dense week grid on mobile | Day agenda remains primary under 900px; blocks keep ≥12px type |
| RTL | Today pill and sticky employee column use logical `start`; empty/hero not LTR-only art |

**Contrast target:** pastel fill + `*-ink` text pairs already used on Jobs/Interviews (proven). Avoid white text on soft yellow/pink.

---

## 6. Implementation plan (this wave)

1. Document shared baseline in ops + CSS comments  
2. Restyle Shifts board hero, ShiftBlock tokens, today ink pill, compact filters, designed empty state  
3. Calm Requests/Planning (softer borders, quieter surfaces)  
4. Preserve all IQ-12 markers/behaviors  
5. Contract test + deploy + smoke + screenshots EN/AR desktop/mobile  

**GO/NO-GO for rolling across post-hire:**  
- **GO** — Shifts is the shared visual baseline reference; reuse `wf-accent-*` / `ph-state-*` tokens.  
- **NO-GO** — do not restyle every post-hire page in this stamp; adopt page-by-page.  
- CalendarShell legacy hex remains out of scope until its own wave.

