# Pre-hiring semantic color map (local pass)

**Stamp:** `20260731T203045Z`  
**Authority:** Overview saturated blocks + shared `wf-accent-*` tokens  
**Out of scope:** Overview (unchanged) · Calendar (complete — do not reopen)  
**Deploy:** **HOLD** until approved

---

## Shared tokens (`index.css`)

Keep cream canvas / dark shell / black CTAs.

| Token | Base | Soft | Ink | Meaning |
|---|---|---|---|---|
| `priority` | `#a9ba7d` | `#dfe8c8` | `#2f3a22` | Open / healthy / go / top-fit / completed |
| `review` | `#f1d96f` | `#f7e89a` | `#3d3410` | Draft / attention / due / needs feedback |
| `assess` | `#e8acd0` | `#f0c4de` | `#4a2438` | Assessment / evaluation / rank #3 |
| `follow` | `#b4c9e5` | `#c9d8ef` | `#243044` | Schedule / follow-up / closed-archive / info |
| `paused` | `#c4b49a` | `#efe8dc` | `#4a4338` | Paused / deferred / cancelled-neutral |
| `active` | `#e2574c` | `#f5ddd7` | `#6b221c` | Critical / reject (sparing) |

**Composition rules**
1. **1–2 larger pastel surfaces per page** (tiles, washes, top-card fills) — not chip-only.
2. Badges stay secondary cues.
3. No gradients; no Overview metric rainbow clone.
4. Pastel surfaces use matching `-ink` text.
5. Assistant suggestion chips: **neutral cream only**.

---

## Page-by-page map + exact token usage

### Jobs — personality: status inventory
| Surface | Token usage |
|---|---|
| Open count tile | `bg-wf-accent-priority-soft` + `text-wf-accent-priority-ink` |
| Draft count tile | `bg-wf-accent-review-soft` + `text-wf-accent-review-ink` |
| Paused count tile | `bg-wf-accent-paused-soft` + `text-wf-accent-paused-ink` |
| Closed count tile | `bg-wf-accent-follow-soft` + `text-wf-accent-follow-ink` |
| Row badges | `Badge tone` → priority / review / paused / muted |
| Board / filters | cream `wf-surface` / `#f8f3e9` — uncolored |

**Do not:** recolor table rows or filter chrome.

### Candidates — personality: quiet list
| Surface | Token usage |
|---|---|
| Board | `Card tone="board"` → `bg-wf-surface` |
| Avatars | cream `#eee5d4` |
| Stage chips | muted default; `ready`→`review`; `hired`→`priority`; `rejected`/`withdrawn`→`danger` |
| Identity attention | tiny `bg-wf-accent-review` dot |

**Do not:** people-band wash; pastel every stage.

### Interviews — personality: schedule ops
| Surface | Token usage |
|---|---|
| Upcoming tile | `bg-wf-accent-follow` + `text-wf-accent-follow-ink` |
| Needs feedback tile | `bg-wf-accent-review` + `text-wf-accent-review-ink` |
| Completed tile | `bg-wf-accent-priority` + `text-wf-accent-priority-ink` |
| Row badges | existing status tones |

**Do not:** solid rainbow queue rows.

### Assessments — personality: send / review
| Surface | Token usage |
|---|---|
| Send panel | `bg-wf-accent-assess-soft` + `text-wf-accent-assess-ink` |
| Needs-review panel | `bg-wf-accent-review-soft` + `text-wf-accent-review-ink` |
| Assessment configuration | cream collapsed shell (`#fffaf0`) |
| Cohort chips | black active / cream idle |

**Do not:** tint suggestion-like chrome; reopen config layout.

### Ranking — personality: top-fit emphasis
| Surface | Token usage |
|---|---|
| Rank #1 card | `bg-wf-accent-priority` + `text-wf-accent-priority-ink` |
| Rank #2 card | `bg-wf-accent-follow` + `text-wf-accent-follow-ink` |
| Rank #3 card | `bg-wf-accent-assess-soft` + `text-wf-accent-assess-ink` |
| Rank #4+ | cream raised surface |
| Score badge | `priority` when scored |

**Do not:** wash the entire results list.

### Reports — personality: quiet leadership board
| Surface | Token usage |
|---|---|
| Boards | cream `#fffaf0` |
| Metric accents | **tiny** dots only: `bg-wf-accent-{priority,review,assess,follow}` |
| Breakdown counts | black pills `bg-[#23211d] text-white` |
| Export counts | black pills (same as breakdowns) |

**Do not:** Overview-style filled metric cards.

### Assistant — personality: calm workspace
| Surface | Token usage |
|---|---|
| Shell | `bg-wf-surface` |
| Empty suggestion chips | `bg-white/45 text-subtle` — **no** `wf-accent-*` |

**Do not:** capability-colored chips.

### Overview / Calendar
| Page | Status |
|---|---|
| Overview | Authority — **unchanged** |
| Calendar | Complete — **do not reopen** |

---

## This pass implementation scope

1. Normalize Jobs status tiles to soft + ink pairs (contrast + consistency).
2. Align Reports export counts to black pills.
3. Lock Assistant chip neutrality + page token contracts in tests.
4. Local EN/AR desktop/mobile capture + contrast checks.
5. **No deploy** until approved.
