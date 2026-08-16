# Assignment-type olive proof — `20260804T175726Z`

## Rule

Olive (`bg-wf-accent-priority-soft`) is applied **only** when
`assignment_type === 'operations'`.

Missing / empty / unknown / free-text / overnight-without-type → normalize to
`general` → **neutral** `bg-wf-frame` (not olive).

## DB coverage — company scheduled (WATHEFNI)

| Bucket | Count |
|---|---:|
| Guest | 9 |
| Operations | 9 |
| Event / Specialty | 8 |
| Night | 9 |
| General | 46 |
| Missing (NULL/blank) | **0** |

Missing is 0 because the column is `NOT NULL DEFAULT 'general'`. Legacy rows
were written as `general` at migration; they are not olive.

## Live UI board (Aug 16–22 week, owner session)

Visible tiles include overnight continuation fragments, so tile counts can exceed
unique shift rows.

| `data-shift-assignment-type` | Tiles | Olive tiles |
|---|---:|---:|
| Guest | 9 | 0 |
| Operations | 10 | **10** |
| Event | 9 | 0 |
| Night | 10 | 0 |
| General | 9 | 0 |
| Missing | 0 | 0 |

- Non-operations olive violations: **0**
- General tiles using olive: **0**
- Sample general class: `bg-wf-frame`
- Sample operations class: `bg-wf-accent-priority-soft`

## Normalize proof

| Input | Normalized | Surface |
|---|---|---|
| `undefined` / `null` / `''` | `general` | neutral frame |
| `scheduled` / `healthy` / `Front desk` | `general` | neutral frame |
| `operations` | `operations` | olive |
