# HR mobile Attendance — backend contract debt

**Status:** Accepted product freeze after canary OTA `130f2835-c810-49e9-be21-1ad0bbf5cb01` (2026-08-10).  
**Rule:** `.cursor/rules/hr-mobile-attendance-ux-freeze.mdc`  
**Do not** invent parallel mobile logic to close these. Track as architecture follow-up.

## Known gaps

| Gap | Current behavior | Desired long-term |
| --- | --- | --- |
| Unresolved lookback | Cap at **92 days** (`UNRESOLVED_LOOKBACK_DAYS` / API window) | Unbounded (or explicit) open-exception feed until handled |
| Mutation path | Mobile resolve → `correct_attendance_record` (often pending review) | Same Ops path as web: request → review → dual if needed → **apply** |
| Identity | Mobile item keyed by `attendance_id` (compat day row) | Optionally surface Ops `exception_id` + case linkage |
| History | No Ops case / dispute / apply timeline on mobile detail | Relevant governed history when mobile decision needs it |
| Kind coverage | Compat projection map: absence, lateness, early_leave, missing punches, incomplete | Also Ops-only kinds when present: `ambiguous_punches`, `connector_issue` |
| Count sources | Home + mobile list use `status=exceptions` on compat attendance; web Ops board uses `attendance_ops_exceptions` | Single canonical exception truth / IDs across Home, Inbox, mobile Attendance, web Ops |

## Explicitly out of mobile scope (web-first)

Full day board · bulk actions · imports · capture · payroll board · heavy governance tooling.
