# HR mobile Shifts — backend contract debt

**Status:** Decision-first companion shipped (Needs Attention + Today).  
**Do not** invent parallel swap/schedule logic to close these. Track as architecture follow-up.

## Known gaps

| Gap | Current behavior | Desired long-term |
| --- | --- | --- |
| Attention kinds | V1 emits **shift swaps only** | Availability, open-shift claims, coverage issues join Needs Attention without IA redesign (`ShiftsAttentionKind`) |
| Nested shifts on list | List API now attaches requester/target shifts (N+1 `shift_by_id`) | Batch hydrate or denormalized swap projection for scale |
| Role / assignment type | Mobile surfaces `assignment_type` or legacy `role` string | Frozen web EN/AR assignment-type labels (`guest` / `operations` / …) when needed |
| Location fields | Falls back across `location` / site / branch when present on row | Stable location display contract from L0 board enrichment |
| Shift detail | Today rows read-only; no `/shifts/{id}` workflow | Optional read-only detail only if product needs it |
| Count parity | Home/Inbox use mobile `list_shift_swaps` scoped items | Confirm totals always match web Requests queue for same actor scope |
| Week / planning | Mobile ignores week query + planning APIs | Remain web-first |

## Explicitly out of mobile scope (web-first)

Week roster board · create/cancel/reschedule · templates · recurrences · draft→publish · open-shift invent/assign · coverage rules · rotations · compliance · PAM · reconciliation tooling.
