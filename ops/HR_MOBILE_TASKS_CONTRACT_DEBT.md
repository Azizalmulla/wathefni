# HR mobile Tasks — backend contract debt

**Status:** open follow-up queue wave shipped (detail + Mark done via canonical resolve).  
**Boundary:** Focused open queue — not Alerts & Delivery recreation; dismiss/assign stay web-first.

## Known gaps

| Gap | Current behavior | Desired long-term |
| --- | --- | --- |
| History | Mobile lists/opens `open` only | Keep — done/dismissed remain web |
| Dismiss | Intentionally omitted on mobile | Remains web-first |
| Assign / reassign | Schema `assigned_to_user_id` unused on mobile | Productize only if owner asks |
| Confirmation store | Client confirm + `expected_status` (documents-style); not HR-2 prepare/confirm store | Optional parity if registry action is introduced |
| Delivery Alerts | Separate quiet More monitor (has_task deduped; not in priorities) | If converging later: fold under Tasks only with has_task dedupe — never a duplicate queue |
| Manager company-wide tasks | `employee_key IS NULL` hidden from restricted managers (list + resolve) | Keep unless product changes HR-only rule |
| Web resolve scope | Web resolve now pre-loads via `get_hr_task` scope (same as mobile) | Keep defense-in-depth |

## Explicitly out of mobile scope (web-first)

Dismiss · assign · reassign · done/dismissed history browse · recreating Alerts & Delivery · outbound message body internals.
