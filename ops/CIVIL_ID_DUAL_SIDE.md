# Civil ID dual-side (front + back)

**Evidence:** `ops/evidence/civil-id-dual-side-20260806T014717Z/`

Employee Civil ID uploads collect **Front** and **Back** under one checklist item. Parts attach to one governed `draft_parts` version; the same version promotes to `pending_hr_review` after the pair gate.

## Flags

| Flag | Purpose |
|---|---|
| `WATHEFNI_CIVIL_ID_DUAL_SIDE` | Master switch |
| `WATHEFNI_CIVIL_ID_DUAL_SIDE_COMPANIES` | Company allowlist |
| `WATHEFNI_CIVIL_ID_DUAL_SIDE_EMPLOYEE_ALLOWLIST` | Employee allowlist |

DocVal soft/hard flags are unchanged. Keep `HARD=off` for canary.

## Prove path

Use disposable item `civil_id_dual_side_canary` via `ops-aziz-civil-id-dual-side-canary.py`. Do not reopen Aziz’s accepted real Civil ID until prove is complete.

## Rollback

Set `WATHEFNI_CIVIL_ID_DUAL_SIDE=off` and reload. Optional canary cleanup script. Snapshot Civil ID SHA before/after.
