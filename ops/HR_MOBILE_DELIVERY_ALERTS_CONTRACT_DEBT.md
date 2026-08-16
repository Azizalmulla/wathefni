# HR mobile Delivery Alerts — contract debt

**Status:** Quiet read-only More monitor locked (2026-08-10).  
**Boundary:** Non-task outbound delivery states only — not HR Tasks, not Home/Inbox, not Settings.

## Locked product shape

| Surface | Behavior |
| --- | --- |
| More | Sole destination when `delivery_alerts` capability enabled |
| Home / Inbox | Never render; backend does not emit `delivery_alerts` into priorities |
| Dedup | Canonical `has_task` / `hr_task_id IS NULL` (same as web Alerts & Delivery) |
| Capability | Same read OR as `hr_tasks` (includes `payroll.read`); actions `["read"]` only |
| UI | Cream/black: employee, channel, status, last attempt, failure/suppression reason |
| Mutations | None — no resolve, resend, or task create from this page |

## Known gaps

| Gap | Current behavior | Desired long-term |
| --- | --- | --- |
| Web Alerts & Delivery parity | Mobile is a thin monitor, not the full web page | If converging: fold under **Tasks only** with `has_task` dedupe — never a second actionable queue |
| Resend / retry | Intentionally omitted | Web-first unless owner opens a mutation wave |
| Linked-task deep link | Linked rows hidden; tasks live under HR Tasks | Keep |
| Pagination total vs belt | SQL exclude is authoritative; client belt filters any residual `has_task` | Keep defense-in-depth |
| Detail page | List-only; optional employee deep-link when present | Keep unless product asks for alert detail |

## Explicitly out of mobile scope (web-first)

Resend · retry · create/resolve HR task from alert · full messaging readiness console · outbound message body internals · Settings/company writers.
