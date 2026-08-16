# R5I module-off proof

- Disable Comp: workspace `resource_state=unavailable`, `counts=None`.
- Historical `cp_cycles` row retained.
- History still reconstructable from canonical rows after disable.
- JA disable after historical cycle: Comp workspace unavailable with `ja_hard_unmet=true`; no guessed worksheet.
- New notifications use R4 module suppression via `flow=compensation_planning`.
- Disable does not reverse applied downstream employment/payroll changes (Comp never applied them).
