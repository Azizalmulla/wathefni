# Schedule visual redesign (match Home energy, not Home layout)

**Stamp:** `20260809T021502Z`  
**Verdict: PASS**

## What changed

1. **Present / Late / Absent** — removed three-up KPI tiles; replaced with one quiet `WindowSummaryLine` (`3 Present · 1 Late · 1 Absent`) with semantic colour on figures only.
2. **Empties** — Today / Upcoming / day empties / calm loading → `QuietEmpty` (no IconBadge white cards). Errors keep `StatusNotice` with semantic edge.
3. **Selected day** — filled day keeps one sky `PastelCard`; empty day is quiet cream statement.
4. **HR note** — demoted to footnote text (no shield card).
5. **Week capsule** — taller stadium (36×58, radius 18) inside 68pt strip.

Home untouched. No backend / permission / pagination changes.

## Deploy

| Field | Value |
| --- | --- |
| Channel | Canary OTA `dff580af-bca4-44dd-94b8-97c5282b9968` · runtime `0.1.0` |
| Rollback | `5263ab51-5a7b-4ed5-8f64-755e09e4a370` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/dff580af-bca4-44dd-94b8-97c5282b9968 |

## Gates

tsc PASS · density PASS (99) · capability GREEN
