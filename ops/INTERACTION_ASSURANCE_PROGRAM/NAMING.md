# Interaction assurance naming

## Mode

Default: **in-tenant synthetics** on `company_code=WATHEFNI` only, gated by markers + phone prefixes.  
Optional: disposable isolation companies (`IAXALPHA` / `IAXBRAVO`) for cross-tenant denial — never mutate real non-WATHEFNI customer tenants.

## Markers

| Field | Value |
|---|---|
| Family | `IAX` |
| Name / key marker | `IAX-SYNTH\|` |
| Employee JSON flag | `iax_synth` |
| Tag | 8-char hex from uuid |
| Example employee key | `WATHEFNI-IAX-{TAG}` |
| Example display name | `IAX-SYNTH\| Emp {TAG}` |

## Phone block

Reserved synthetic range: **`965542`** (do not reuse attendance/leave/shifts/payroll wave ranges).

Example: `965542` + 5 digit-safe tag chars → unique per run.

## Forbidden

- Real WATHEFNI employees (Aziz/Talal/demo seeds without IAX marker)
- Real customer tenants
- Deleting rows outside marker + phone scope
- Leaving operational synthetic leftovers after canary cleanup
