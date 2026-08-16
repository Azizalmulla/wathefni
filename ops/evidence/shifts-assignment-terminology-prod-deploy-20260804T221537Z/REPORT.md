# Shifts assignment terminology — production deploy + permanent UX freeze

**Stamp:** `20260804T221537Z`  
**Bundle:** `PostHire-6cAbY2Uo.js`  
**Scope:** User-facing EN/AR labels only. Stored `assignment_type` keys, colors, filters, backend, IQ-12 unchanged.

## Labels

| Key | EN | AR |
| --- | --- | --- |
| guest | Customer-facing | خدمة العملاء |
| operations | Operations | العمليات |
| event | Special assignment | مهمة خاصة |
| night | Night | ليلي |
| general | General | عام |

Conflict remains status: Conflict / تعارض.

## Proof

| Check | Result |
| --- | --- |
| Unit tests | 27 passed |
| Bundle markers | `TERMINOLOGY_SMOKE_OK` (old Guest/ضيوف absent) |
| Health `:8010/health` | 200 |
| Stored option values | guest/operations/event/night/general |

## Permanent freeze

Shifts UX track closed. See `ops/SHIFTS_UX_PERMANENT_FREEZE.md` and `.cursor/rules/shifts-freeze.mdc`.

## Rollback

```bash
/opt/wathefni/backups/production-pre-shifts-assignment-terminology-20260804T221537Z/ROLLBACK.sh
```
