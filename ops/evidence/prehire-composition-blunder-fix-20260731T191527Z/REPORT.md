# Composition blunder fix — production deploy

**Stamp:** `20260731T191527Z`  
**Live chunk:** `dashboard-CsSPSgK4.js`  
**Scope:** Assessments full-card pink fill + framed-shell vertical scroll for Reports overflow

## Fixes
1. **Assessments Ready to send** — whole card is one assess-soft surface (no inset pink header island); rows sit on white/55 within the same card.
2. **Needs review** — same pattern with review-soft full card.
3. **Reports spill** — content pane `min-h-0 overflow-y-auto` so long breakdowns scroll inside the framed shell instead of escaping the rounded panel.

## Gates
See `remote/markers.json` — health/dashboard 200, markers PASS.

**Final live chunk after needs-review list patch:** `dashboard-DC-FCVKk.js`
