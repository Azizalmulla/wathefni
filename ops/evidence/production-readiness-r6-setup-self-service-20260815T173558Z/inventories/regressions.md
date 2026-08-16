# R6 regressions

All listed gates are 0 failed.

## Local / qualify units

| Suite | Result |
|---|---|
| R6 Setup self-service | 63 / `R6_SETUP_SELF_SERVICE_UNIT_PASS` |
| R5A capability honesty | 146 / `R5A_CAPABILITY_HONESTY_UNIT_PASS` |
| R5B–R5J surfaces | 56 / 62 / 70 / 78 / 92 / 89 / 97 / 108 / 112 |
| Wave 1–6 product acceptance | 28 / 47 / 42 / 50 / 50 / 54 |
| Wave 6 C1–C7 | 27 / 35 / 36 / 33 / 33 / 39 / 40 |
| Intelligence C1–C6 | 23 / 14 / 17 / 15 / 16 / 19 (empty allowlist admits after R6) |
| Talent C5/C6 | 21 / 27 |
| R2 / R3 / R4 units | 84 / 61 / 40 |
| Interaction authority contracts | rc=0 |

## Staging DB

| Suite | Result |
|---|---|
| R6 A–G | 42 / `R6_SETUP_SELF_SERVICE_DB_PASS` |
| R5J–R5A DB | 94 / 74 / 87 / 87 / 75 / 74 / 81 / 63 / 62 / 30 |
| R2 / R3 / R4 DB | 69 / 18 / 9 |
| Internal auth | 10 / ALL CHECKS PASSED |

## Clients

| Suite | Result |
|---|---|
| Dashboard vitest full | 89 files / 481 tests |
| Employee composition | 71 checks |

## Live staging

7/0 — WFP, Comp, JA still enableable; unreleased empty; Setup routes not public.

Frozen authority was not rewritten. Empty Intelligence allowlist invert is the only Wave 5 gate-semantics change.
