# Semantic color layer — local implement evidence

**Stamp folder:** `20260731T133500Z`  
**Implement stamp:** see `IMPLEMENT_STAMP.txt`  
**Deploy:** **LIVE** via `ops/evidence/prehire-semantic-color-deploy-20260731T134127Z/` (`20260731T134127Z`)

Color map (approved direction for this pass): [`COLOR_MAP.md`](./COLOR_MAP.md)

---

## Shared palette (meaning)

| Token | Meaning |
|---|---|
| `wf-accent-priority` (+ soft/ink) | Healthy / open / go / top-fit |
| `wf-accent-review` | Draft / needs review / attention |
| `wf-accent-assess` | Assessment / evaluation |
| `wf-accent-follow` | Follow-up / schedule / info |
| `wf-accent-active` | Critical urgency (sparing) |
| `wf-accent-paused` | Paused / deferred / closed-soft |
| `wf-surface-raised` | Important row/card vs cream board |

Canvas, dark shell, and black primary actions unchanged.

---

## What changed (structure/logic untouched)

| Area | Change |
|---|---|
| `index.css` | Soft/ink companion tokens + paused + surface-raised |
| `Badge` / `StatusPill` | Semantic Wathefni tones (priority/review/assess/follow/paused/active) |
| Jobs | Status tones → open/draft/paused/closed mapping |
| Candidates | Stage tones + raised hover + soft avatar |
| Calendar | Event cards pastel by type/status (cream board kept) |
| Assessments | Progress/eval badges → assess/priority |
| Ranking | Top-3 left rail + rank pill accents |
| Reports | QuietMetric left-rail accents (quieter than ops pages) |
| Assistant | Capability-family tinted suggestion chips |
| Overview | Preserved (authority) |

---

## Verification

| Gate | Result |
|---|---|
| Production build | **PASS** (`verify/build.log`) |
| Focused Vitest (Jobs + Assistant contract) | **PASS** 16/16 |
| Before screenshots (prod live) | `screenshots/before/` |
| After screenshots (local dist) | `screenshots/after/` EN+AR desktop; mobile for jobs/candidates/calendar/ai |
| EN/AR `dir` | Probed in `verify/after-probes.json` |
| Contrast | Soft fills paired with dedicated ink tokens (`*-ink`); black primary CTAs unchanged |
| Layout/logic | No structural redesign |

---

## Deploy recommendation

**DEPLOYED** `20260731T134127Z` — see `ops/evidence/prehire-semantic-color-deploy-20260731T134127Z/REPORT.md`.
