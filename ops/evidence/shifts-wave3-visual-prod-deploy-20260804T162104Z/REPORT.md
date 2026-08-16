# Shifts Visual Design Wave 3 — evidence report

**Stamp:** `20260804T162104Z`  
**Verdict:** **GO** for Shifts as shared post-hiring visual baseline reference  
**Live bundle:** `PostHire-Cjhqi0Um.js` via `WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist`  
**Smoke:** `SHIFTS_WAVE3_VISUAL_SMOKE_OK` · IQ-12 preserved (`SHIFTS_WAVE2_IQ_SMOKE_OK`)  
**Prerequisite IQ-12 stamp:** `20260804T155956Z` (behaviors preserved; live path corrected)

## What shipped

- Shared post-hire palette aliases in `index.css` (`ph-state-*` → pre-hire `wf-accent-*`)
- `visualBaseline.ts` semantic shift surfaces (priority/review/assess/follow/paused)
- Schedule board as visual hero (raised surface, ink today pill, designed empty state)
- Compact filter + date chrome; calmer Requests/Planning canvases
- Markers: `data-shifts-visual-wave3`, `data-shifts-board-hero` (+ IQ-12 markers retained)

## Deploy paths

| Path | Role |
|---|---|
| `/opt/wathefni/dashboard-dist` | **Live** (uvicorn `:8010`) — primary deploy |
| `/var/www/wathefni-dashboard` | Mirror (kept in sync) |

**Note:** Prior Wave 2 IQ stamp targeted `/var/www`; production process env still points at `dashboard-dist`. Wave 3 corrected live path.

## Backups / rollback

```bash
# Preferred (live)
rsync -a --delete /opt/wathefni/backups/production-pre-shifts-wave3-visual-dashboard-dist-20260804T162104Z/ /opt/wathefni/dashboard-dist/

# Mirror
rsync -a --delete /opt/wathefni/backups/production-pre-shifts-wave3-visual-20260804T162104Z/ /var/www/wathefni-dashboard/
```

## Screenshots

| | Desktop EN | Desktop AR | Mobile EN | Mobile AR |
|---|---|---|---|---|
| Before | `before/before-schedule-desktop-en.png` | `before/before-schedule-desktop-ar.png` | `before/before-schedule-mobile-en.png` | `before/before-schedule-mobile-ar.png` |
| After Schedule | `after/after-schedule-desktop-en.png` | `after/after-schedule-desktop-ar.png` | `after/after-schedule-mobile-en.png` | `after/after-schedule-mobile-ar.png` |
| After Requests | `after/after-requests-desktop-en.png` | `after/after-requests-desktop-ar.png` | `after/after-requests-mobile-en.png` | `after/after-requests-mobile-ar.png` |

## GO / NO-GO — roll across all post-hiring pages

| Decision | Verdict |
|---|---|
| Keep Wave 3 as **Shifts reference baseline** | **GO** |
| Immediately restyle every post-hire page this stamp | **NO-GO** (page-by-page adoption) |
| Adopt shared tokens (`wf-accent-*` / `ph-state-*`) for next post-hire visual wave | **GO** |

Rollout rule: reuse the shared token contract; do not invent page-local hex. CalendarShell legacy hex remains out of scope until its own wave.
