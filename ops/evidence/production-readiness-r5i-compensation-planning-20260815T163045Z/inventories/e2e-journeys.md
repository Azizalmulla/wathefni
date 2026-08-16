# R5I E2E journeys A–G

Proved on staging tenant `R5I150018` (`R5I_COMPENSATION_PLANNING_SURFACE_DB_PASS`, 74/0).

| Journey | Result |
|---|---|
| A Planning cycle | JA required before enable → grade + Comp band → KWD cycle → freeze eligible pop (1 eligible / 1 ineligible) → budget 200 → over-budget 500 hard-blocked → recommend 50 → budget recommended=50. Empty manager = zero rows; scoped manager sees E1 only |
| B Calibration | Original recommendation preserved; calibrated layer distinct (`original_preserved=true`) |
| C Approval | Same-actor approve SOD blocked → other approver succeeds → finalize `applied=false` → no salary/payroll mutation |
| D Handoff | Payroll OFF blocks `wathefni_payroll` → `employment_change_c1` package created, not applied → replay idempotent → execution `any_applied=false` / `any_payroll_paid=false` → Payroll ON creates explicit payroll handoff, still not paid |
| E Performance/Talent | Second cycle with advisory rating/HiPo context. `hipo_auto_convert` fails. Guided recommend allowed without auto formula |
| F Payroll OFF | Full plan/finalize works before payroll handoff enablement; wathefni_payroll blocked until settings allow explicit handoff |
| G Historical | Band v2 does not rewrite launched snapshot base/version. History reconstructable. Disable: workspace `unavailable` / `counts=None`, cycle retained, history still reconstructable. JA off → Comp unavailable, no guessed worksheet |

Also proved: HTTP unauthenticated not public; HR without `comp_planning.*` 403 is not empty-cycles; manager admin 403; export without `.export` is 403; USD create 422 `currency_unsupported_no_fx`; tenant isolation; assistant mutation forbidden.
