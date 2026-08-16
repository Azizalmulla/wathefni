# Semantic color layer — composition map (corrected)

**Stamp:** `20260731T185000Z` (composition correction)  
**Authority:** Overview saturated blocks + HR/employee mobile pastels + Intelly calendar fills  
**Constraint:** Cream canvas, dark shell, black CTAs unchanged · **no deploy until approved**  
**Assistant:** suggestion chips stay **neutral** (no capability tint)

---

## Shared palette

Keep: cream (`wf-canvas` / `wf-frame` / `wf-surface`), dark shell (`wf-sidebar`), black primary (`wf-ink`).

| Token | Base (Overview-grade) | Soft wash (panels) | Ink | Meaning |
|---|---|---|---|---|
| `priority` | `#a9ba7d` | `#dfe8c8` | `#2f3a22` | Healthy / open / go / top-fit |
| `review` | `#f1d96f` | `#f7e89a` | `#3d3410` | Draft / attention / due |
| `assess` | `#e8acd0` | `#f0c4de` | `#4a2438` | Assessment / evaluation |
| `follow` | `#b4c9e5` | `#c9d8ef` | `#243044` | Schedule / follow-up / info |
| `active` | coral soft `#F5DDD7` | — | `#6b221c` | Critical / today (sparing) |
| `paused` | `#EFE8DC` | — | `#4a4338` | Paused / deferred |
| Mobile brand (sparing) | plum `#74415F` / pink `#AA477F` | `plumSoft` `#F0DDE8` | — | Brand moments only, not page wash |

**Composition rules (corrected)**
1. **1–2 noticeable larger pastel surfaces per page** — panels, summary tiles, event cards, selective full-card washes — **not** chip-only.
2. Badges may stay tinted as secondary cues; they are not the page personality.
3. No gradients; do not clone Overview’s full metric rainbow onto every page.
4. Text on pastel must use ink-on-soft pairs above.
5. Assistant suggested-action chips: **neutral cream only**.

---

## Page-by-page composition

| Page | Larger surfaces (1–2) | Secondary | Do not |
|---|---|---|---|
| **Overview** | Keep existing saturated cards | — | Add more pastels |
| **Jobs** | Status count tiles (open/draft/paused) as pastel blocks above list | Status badges | Recolor whole table |
| **Candidates** | Cream board list; filters uncolored; stage muted except review/hired/danger | Small cream avatar; review warning = tiny dot + text | Blue people-band wash / pastel every stage |
| **Interviews** | Summary info tiles filled (follow / review / priority) | Status badges | Solid rainbow queue |
| **Calendar** | Colored event **cards** (near base accent, Intelly-style) | Status micro-pill | Paint cream board |
| **Assessments** | Send/review panel wash (assess pink); attention strip (review yellow) | State badges | Extra black-pill chrome |
| **Ranking** | Top-3 **full-card** priority/follow washes | Rank chip | Recolor entire list |
| **Reports** | Quiet cream boards; ink metrics; **tiny** pastel dots only (no rainbow tiles) | Black count pills | Full pastel metric cards / Overview clone |
| **Assistant** | Cream chat shell only | Neutral suggestion chips | Colored suggestion chips |

---

## Implementation (this pass)

Local only. Capture before/after after build. Hold deploy.
