# Shifts Assignment Type — Governed Model

**Status:** Implemented with Wave UX visual direction deploy  
**Authority:** Additive L0 field only — does not change conflict, cancel, leave, or IQ-12 contracts

## Why this exists

Healthy-tile color rhythm must not be inferred from free-text `role` / `location` or by employee.
EN and AR labels must resolve to the same underlying category key.

## Model

| Field | `shift_assignments.assignment_type` |
|---|---|
| Type | `text NOT NULL DEFAULT 'general'` |
| Check | `IN ('guest','operations','night','event','general')` |
| Legacy / missing / custom role | **`general`** (neutral frame cream) |
| Write path | Dashboard create composer select; WhatsApp/API action may pass the same key |
| Invalid write | Rejected (`invalid_assignment_type`) — never silently remapped from free text |

## Category → visual (healthy only)

| Key | EN label | AR label | Soft surface |
|---|---|---|---|
| `guest` | Guest / front of house | ضيوف / استقبال | review soft (warm yellow) |
| `operations` | Operations / floor | عمليات / صالة | priority soft (olive) |
| `night` | Night | ليلي | follow soft (muted blue) |
| `event` | Event / specialty | فعالية / تخصص | assess soft (dusty pink) |
| `general` | General | عام | frame cream (neutral) |

## Exception overrides (always win)

| `ui_state` | Treatment | Also shown as text |
|---|---|---|
| `conflicted` | review yellow fill | Conflict / تعارض |
| `reconciliation_required` | assess pink fill | Review / مراجعة |
| `cancelled` | paused taupe fill | Cancelled / ملغاة |

Color is never the only state signal for exceptions.

## Explicitly out of scope

- Keyword / fuzzy matching on role text
- Coloring by employee identity
- Using overnight span (`ends_next_day`) as a category substitute
- Changing schedule mutation authority beyond accepting this optional field

## Backfill

No automatic backfill. Operators set `assignment_type` on new shifts via the composer.
Existing rows remain `general` and stay readable.
