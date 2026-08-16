# Calendar UX — permanent freeze

**Status:** Calendar product UX / visual system is **PERMANENTLY FROZEN**  
**Freeze stamp:** `20260805T003730Z`  
**Prior Wave 1b freeze:** `ops/CALENDAR_WAVE1B_UX_CLOSURE_FREEZE.md` · `20260804T223738Z`  
**Cursor gate:** `.cursor/rules/calendar-freeze.mdc`

## Final live surface (do not reopen without owner change-control)

| Layer | Frozen |
|---|---|
| Day / week / month layouts | Yes |
| Event-card variants (`solo-short` / `solo-medium` / `solo-long` / `cascade` / `all-day` / `month`) | Yes |
| Category rails + Wathefni token surfaces | Yes |
| All-day row split from timed lane | Yes |
| Overlap cascade + `+N` overflow menu | Yes |
| Selected-event lifecycle (`selectedId` authority) + portal drawer | Yes |
| Soft-keep, polling, scroll restoration, view/scope/filter transitions | Yes |
| Calendar CRUD + Interview ownership gates | Yes |
| Toolbar composition + shared token system | Yes |

## Populated preview (canary mechanism only)

- Module retained: `wathefni-orchestrator/calendar_populated_preview.py`
- Flag retained: `WATHEFNI_CALENDAR_POPULATED_PREVIEW` (+ `…_COMPANIES`)
- **Normal production visibility:** flag **off** — no synthetic `calprev-` events in live Calendar
- Future testing: set flag `on` for allowlisted companies only; never write real module rows

## Hard bans

1. Do not reopen Calendar chrome, card anatomy, week density, drawer lifecycle, or soft-keep contracts without a new owner wave.
2. Do not add leave / onboarding / compliance / payroll / shifts calendar emitters without Calendar Wave 2 owner change-control.
3. Do not weaken Interview schedule authority or `calendar.sync` owner-only.
4. Do not reintroduce local hex category fills, opacity-flash refresh chrome, or non-portal drawer mounts.
5. Do not enable populated preview for normal production visibility (keep mechanism off unless explicitly testing).
6. Do not fold specialist-module mutations into Calendar.

## Allowed without a new wave

- Bugfixes restoring freeze invariants
- Ops evidence / documentation
- Unit / contract smokes under `Calendar*.test.*`
- Kill switches and `ROLLBACK.sh` from production backups
- Temporary re-enable of populated preview for canary QA only

## Rollback

```bash
/opt/wathefni/backups/production-pre-calendar-ux-permanent-freeze-20260805T003730Z/ROLLBACK.sh
```

## Evidence

`ops/evidence/calendar-ux-permanent-freeze-prod-deploy-20260805T003730Z/`
