# Employee App — Onboarding hierarchy refine

**Stamp:** `20260809T050027Z`  
**Verdict:** **PASS** (canary OTA)

## Scope

Visual hierarchy / density only. Lifecycle, authority, routes, permissions, EN/AR/RTL, and seeded fixture unchanged.

## Visual rhythm

| Section | Treatment |
|---|---|
| Overall progress | Soft powder-blue card (`scheduleComposition.planned`) — pink reserved for attention |
| Your actions | Cream rows + thin pink accent; **only** replacement/rejected gets stronger pink bar + pink life mark |
| Being reviewed | Quiet cream rows + muted blue accent; whole-row preview (chevron), no black buttons |
| Handled by company | Flatter rows + soft blue accent |
| Completed | Quietest compact rows + green accent + quiet green settled mark |

## Actions

- One strong primary (`Upload` / `Resubmit` / `Open bank`)
- Preview / Version history → inline underlined `QuietTextAction`

## Fixture (unchanged)

`WATHEFNI-9655237101` · phone `9655237101` · re-run seed for a fresh activation code if expired.

## OTA / rollback

| | |
|---|---|
| Update group | `28a28073-d4bf-47c1-ba16-f95f4c69ffbc` |
| Rollback | `da7d44f0-69d2-4379-80a6-77ef7a85ee19` |
| Gates | density PASS · capability PASS · color PASS · auth-wave2 dist PASS |
