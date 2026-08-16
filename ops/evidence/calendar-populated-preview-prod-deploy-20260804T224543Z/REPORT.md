# Calendar Wave 1 — Populated Preview (WATHEFNI canary)

**Stamp:** `20260804T224543Z`  
**Live URL:** https://api.wathefni.ai/dashboard/ (Calendar)  
**Flag:** `WATHEFNI_CALENDAR_POPULATED_PREVIEW` (companies: `WATHEFNI_CALENDAR_POPULATED_PREVIEW_COMPANIES=WATHEFNI`)  
**Calendar bundle:** `CalendarShell-CvY8fBUf.js`  
**Dashboard:** `dashboard-jJtFkPNg.js`  
**Wave 1b preserved:** sticky drawer, scroll restore, token colors, freshness soft-poll unchanged

## What shipped

- In-memory synthetic post-hire + recruiting density for **WATHEFNI only**
- All synthetic titles/chips labeled **Preview** / **معاينة**
- **No** `calendar_events` / specialist module writes (`db_*_hits=0`)
- **No** new production emitters (leave/onboarding/compliance/payroll/shifts)
- Manual Calendar CRUD + Interview ownership preserved; preview events are read-only (`preview_event_readonly`)
- Month / week / day density with overlaps + empty Sunday; EN/AR RTL via existing shell

## Proof

| Check | Result |
| --- | --- |
| Unit smoke | passed (`tests/unit-local.out`, `tests/live-smoke.out`) |
| WATHEFNI inject | 9 events in current window |
| Other tenant | ACME inject=0 |
| DB rows calprev / Preview | 0 / 0 |
| Bundle banner + tokens | present |
| Health | 200 |
| Flag live | `on` / companies `WATHEFNI` |

## Instant disable

```bash
# Preferred kill: set flag off and restart
sed -i 's/WATHEFNI_CALENDAR_POPULATED_PREVIEW=on/WATHEFNI_CALENDAR_POPULATED_PREVIEW=off/' \
  /etc/systemd/system/wathefni-orchestrator.service.d/zzzz-calendar-populated-preview.conf
systemctl daemon-reload && systemctl restart wathefni-orchestrator
# Or remove drop-in entirely, then restart
```

## Full rollback

```bash
/opt/wathefni/backups/production-pre-calendar-populated-preview-20260804T224543Z/ROLLBACK.sh
```

## Constraints honored

- Wave 1b freeze untouched (no hex fills, no opacity flash, no real post-hire emitters)
- Preview is observation-only for design/density review ahead of Wave 2 projection planning
