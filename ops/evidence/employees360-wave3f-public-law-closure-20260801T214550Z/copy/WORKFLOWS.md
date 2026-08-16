# Workflows — Wave 3F

## Normal-case Kuwait private-sector lifecycle

1. HR confirms Kuwait private-sector jurisdiction (Arts. 2–5).
2. HR completes employment classification: contract type, pay frequency, probation status/dates.
3. For termination: enter `termination_case_class`, effective date, last working day.
4. Impact preview + written impact acknowledgement (dual approval, no self-approval).
5. Notice guidance remains **hidden** unless policy enables hints **and** eligibility rules pass.
6. Approver (different user) approves.
7. On commit: access revoke scheduled; **inputs-only** settlement packet handed to Payroll; Art. 54 service-certificate row `pending`.
8. Cancel-before-effective uses `cancel_scheduled` (same employment preserved).
9. Post-effective path: **true rehire** (new employment); reinstate disabled by default.
10. Documents retained (Art. 80); no auto-purge; floor ≥ 365 days (Art. 144).

## Exceptional / high-risk manual workflow

Cases: `summary_dismissal_41a/41b`, `abandonment_42`, `worker_summary_exit_48`, `death_disability_49`, `employer_status_50`, `other_exceptional`.

1. Software **refuses** to proceed without `exceptional_escalation_note`.
2. UI shows exceptional banner — Wathefni will **not** decide lawfulness.
3. HR attaches evidence; human legal judgment outside product decision authority.
4. Dates, approvals, and Payroll inputs remain human-owned.
5. Notice guidance forced hidden for exceptional classes.
6. Settlement packet still inputs-only; flags `exceptional_case=true`.

## Remaining ambiguities (narrowed to exceptional / Payroll)

1. Exact Official Gazette Arabic for Law 17/2018 Art. 51 — Payroll owns EOSB regardless.
2. Whether a specific Art. 41/42/48 ground is met — intentional human judgment.
3. Legal continuity of post-effective “reinstate” (visa / indemnity) — product keeps reinstate disabled.
4. Retention years beyond the one-year lawsuit horizon — product retains indefinitely; floor 365.
5. Working-day vs calendar-day ops for probation 100-day count — HR calendar; software stores dates only.
