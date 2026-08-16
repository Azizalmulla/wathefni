# Shifts UX — permanent freeze

**Status:** Shifts product UX track is **PERMANENTLY FROZEN**  
**Authority freeze (unchanged):** `ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` · stamp `20260803T033336Z`  
**UX permanent freeze stamp:** `20260804T221537Z` (assignment terminology final amendment)  
**Prior UX closure stamp:** `20260804T221012Z`  
**Cursor gate:** `.cursor/rules/shifts-freeze.mdc`

## Final live surface (do not reopen without owner change-control)

| Layer | Frozen at |
|---|---|
| Controlled authority / allowlists | `20260803T033336Z` |
| Page IA + Wave 3B roster composition | through `20260804T170817Z` |
| Soft-keep navigation | `20260804T183521Z` |
| Assignment-type color model | `20260804T175726Z` |
| UX closure (chrome / rail / empty grid / drawer) | `20260804T221012Z` |
| Industry-neutral assignment **labels** (EN/AR) | `20260804T221537Z` |

### User-facing assignment labels (terminology only)

| Stored `assignment_type` | English | Arabic |
|---|---|---|
| `guest` | Customer-facing | خدمة العملاء |
| `operations` | Operations | العمليات |
| `event` | Special assignment | مهمة خاصة |
| `night` | Night | ليلي |
| `general` | General | عام |

**Conflict** remains a **status** (`conflicted` / `statusConflictShort` → Conflict / تعارض), never an assignment type.

Stored keys, color mapping (`visualBaseline` / `wf-accent-*`), filters, backend contracts, IQ-12, and existing shifts are unchanged.

## Hard bans

1. Do not reopen Shifts UX chrome, roster composition, drawer density, or assignment terminology without a new owner wave.
2. Do not change stored `assignment_type` keys or invent new types to “match labels.”
3. Do not fold Conflict into assignment types.
4. Do not weaken controlled-rollout freezes (managers, timers, PAM, Payroll money, notify allowlists).
5. Do not reopen Attendance / Leave / Onboarding / Employees 360 / AnyDoc to unblock Shifts cosmetics.

## Allowed without a new wave

- Bugfixes restoring freeze invariants
- Ops evidence / documentation
- `smoke-test-shifts-freeze-regression.py`
- Kill switches and `ROLLBACK.sh` from production backups

## Rollback (terminology amendment)

```bash
/opt/wathefni/backups/production-pre-shifts-assignment-terminology-20260804T221537Z/ROLLBACK.sh
```

## Evidence

- Terminology deploy: `ops/evidence/shifts-assignment-terminology-prod-deploy-20260804T221537Z/`
- UX closure deploy: `ops/evidence/shifts-ux-closure-prod-deploy-20260804T221012Z/`
