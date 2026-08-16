# R5J module-off proof

- Disable WFP: workspace `resource_state=unavailable`, `counts=None`.
- Historical plan / scenario / demand / approval / handoff rows retained.
- History still reconstructable from canonical C7 rows after disable.
- Linked draft requisitions are not deleted.
- Executed downstream Recruiting / employment / payroll changes are not reversed (WFP never applied them).
- New notifications use R4 module suppression via `flow=workforce_planning`.
- JA disable after historical plans: WFP workspace unavailable; no guessed title-based catalog.
- WFP works with Recruiting OFF, Compensation Planning OFF, Talent OFF, Payroll OFF, Performance OFF, and unrelated modules OFF.
