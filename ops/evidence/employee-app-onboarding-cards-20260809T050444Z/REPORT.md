# Employee App — Onboarding cards restore

**Stamp:** `20260809T050444Z`  
**Verdict:** **PASS** (canary OTA)

## Scope

Visual correction only. Restore premium card composition with lifecycle-mapped colours. Authority, lifecycle, routes, interaction (soft refresh / latest-wins) unchanged. Fixture unchanged.

## Colour map

| Surface | Fill |
|---|---|
| Progress | Soft powder blue (`SoftBlueCard`) |
| Your action (normal) | Warm yellow (`PastelCard` butter) |
| Needs correction | Pink (`PastelCard` pink) |
| Being reviewed | Soft blue |
| Handled by company | Soft blue (slightly quieter) |
| Completed | Cream + quiet green status mark |

## Actions (kept from hierarchy refine)

- One strong primary (`Upload` / `Resubmit` / Bank)
- Preview / Version history → inline `QuietTextAction`

## OTA / rollback

| | |
|---|---|
| Update group | `96703a6f-3f52-4c1f-8e64-8aa72000ad7e` |
| Rollback | `28a28073-d4bf-47c1-ba16-f95f4c69ffbc` |
| Gates | density PASS · capability PASS · color PASS · auth-wave2 dist PASS |
