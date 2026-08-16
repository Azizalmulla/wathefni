# HR mobile Document Reviews — backend contract debt

**Status:** needs_review compliance queue wave shipped (preview/download + mark reviewed + onboarding-fallback routing).  
**Boundary:** Focused Document Reviews surface — not the full compliance register.

## Known gaps

| Gap | Current behavior | Desired long-term |
| --- | --- | --- |
| Write confirmation | Client confirm sheet + `expected_status` stale check; registry `compliance_mark_reviewed` executes once (non-sensitive) | Keep unless product requires prepare/confirm store parity with leave/onboarding |
| Remind | Intentionally omitted on mobile | Remains web-first (`compliance_send_reminder`) |
| Register browse | Mobile list defaults to `needs_review` only | Optional filtered browse later if product needs it |
| Onboarding-only tenants | Preview/context rows route to `/onboarding/{key}`; no Accept/Waive on Documents | Keep — single decision home for onboarding |
| Label vs name | Adapter emits `label`; mobile normalizes to `name` | Optional dual-field consistency |
| Reminder history | Surfaces `last_reminded_at` / count when present; no send action | Web sends + richer audit trail |
| File absence | Detail shows empty file state when no `preview_path` | Clearer “awaiting upload” copy when status explains it |

## Explicitly out of mobile scope (web-first)

Send Reminder · bulk review · full compliance register · policy config · extraction re-run · employee renewals (employee app surface).
