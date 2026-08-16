# STATUS — Bank visual + interaction

| Field | Value |
| --- | --- |
| Stamp | `20260809T042111Z` |
| Verdict | **PASS** |
| OTA | `997f5309-4818-46e6-8e48-348093ccebd8` |
| Rollback | `0561f73f-4b2b-4592-896c-874244ab2639` |
| Runtime | `0.1.0` · canary channel · JS-only |
| Gates | density PASS · capability PASS · color PASS |
| Authority | Bank ESS lifecycle / permissions / IBAN / masking / routes **unchanged** |

## Visual
- Cream foundation; one butter account summary (`PastelCard`)
- Flat cream ledger blocks (no stacked white panels)
- Calm life marks: action=pink · review=butter · settled=quiet green
- Softer employee-facing status copy (hides HR/payroll jargon in chips)

## Interaction
- Soft invalidate after evidence upload (no blocking `await refetch` before form settles)
- Latest-wins evidence open (`openGeneration`)
- Edit/submit still optimistic via `setQueryData`; scroll/lifecycle preserved

## Seeded states
| Account | Phone | Code | State |
| --- | --- | --- | --- |
| Noura `WATHEFNI-96550010001` | `96550010001` | `135551` | **effective + pending_hr** |
| Synth `…7001` | `9655497001` | `703374` | **effective + pending_payroll** |
| Synth `…7002` | `9655497002` | `529216` | **needs_correction** |
| Synth `…7003` | `9655497003` | `402183` | **applied/effective (clean)** |

Aziz/Talal untouched. Fixture cleanup: `ops-seed-bank-visual-fixture.py --cleanup`
