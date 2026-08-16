# Pre-hire semantic color pass — local qualification

**Stamp:** `20260731T203045Z`  
**Deploy:** **HOLD** — do not deploy until approved  
**Verdict:** **PASS**

Map: [`COLOR_MAP.md`](./COLOR_MAP.md)

---

## Scope

| In | Out |
|---|---|
| Jobs · Candidates · Interviews · Assessments · Ranking · Reports · Assistant | Overview (authority) · Calendar (complete) |
| Cream canvas + dark shell preserved | Layout / logic / permissions / APIs / workflows |

---

## What changed in this pass

Most page personalities were already live from prior semantic composition. This pass closes remaining drifts only:

| Page | Change |
|---|---|
| **Jobs** | Status tiles normalized to **soft + ink** (`priority/review/paused/follow-soft`) — was uneven (open/draft base, paused/closed soft) |
| **Reports** | Export counts → **black pills** (`bg-[#23211d]`) matching breakdowns — was muted `Badge` |
| **Candidates / Interviews / Assessments / Ranking / Assistant** | Token usage locked via contract tests; no layout reopen |

---

## Exact token usage (summary)

See full map in `COLOR_MAP.md`. Anchors:

- **Jobs:** soft pastel status tiles + existing status badges  
- **Candidates:** cream board; muted stages; `review` / `priority` / `danger` outcomes only  
- **Interviews:** filled `follow` / `review` / `priority` summary tiles  
- **Assessments:** `assess-soft` send + `review-soft` needs-review panels  
- **Ranking:** top-3 `priority` / `follow` / `assess-soft` washes  
- **Reports:** tiny accent dots + black count pills (quiet)  
- **Assistant:** neutral `bg-white/45` chips — no capability tint  

---

## Verification gates

| Gate | Result | Evidence |
|---|---|---|
| Production build | **PASS** | `verify/build.log` · chunks in `verify/local-chunks.json` |
| Vitest (semantic + Reports + Assistant contracts) | **PASS** 20/20 | `verify/vitest.log` |
| Contrast (12 ink-on-soft/base pairs, WCAG AA 4.5:1) | **PASS** | `verify/contrast.json` |
| Before screenshots (live prod) | **PASS** 28 + export detail | `screenshots/before/` |
| After screenshots (local dist) | **PASS** 28 + export detail | `screenshots/after/` |
| EN/AR | **PASS** (`ar` → `rtl`) | `verify/before-probes.json`, `verify/after-probes.json` |
| Desktop + mobile | **PASS** all 7 scoped pages | `*-desktop.png` / `*-mobile.png` |
| Layout/logic/API | Unchanged | visual + token-only edits |

### Notable before → after

- **Jobs:** open/draft tiles softer (base → soft) — `jobs-*-desktop.png`  
- **Reports exports:** muted “N records” badges → black numeric pills — `reports-en-desktop-exports.png`  
- **Assistant:** chips remain neutral cream — `ai-*-desktop.png`  

---

## Local build markers

```json
{
  "jobs": "JobsPage-DBa-Hljw.js",
  "reports": "ReportsPage-B-piDZZn.js",
  "dashboard": "dashboard-BKkQL2X2.js"
}
```

---

## Deploy recommendation

**Do not deploy yet.** Awaiting explicit approval.

When approved: dashboard dist only (Jobs + Reports chunks + CSS if hashed); no orchestrator change; Calendar/Overview untouched.
