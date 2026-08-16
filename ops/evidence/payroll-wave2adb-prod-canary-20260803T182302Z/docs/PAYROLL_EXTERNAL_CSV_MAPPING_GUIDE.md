# External Payroll Run — CSV mapping guide (operators)

**Wave:** 2A-D Operability  
**Money:** External system pays. Wathefni does not.

## Input package (download from Wathefni)

| Column | Meaning |
|---|---|
| `employee_key` | Employee id (same key your payroll system uses) |
| `component_code` | Earnings/deduction code from approved contract |
| `component_kind` | Component category |
| `amount_unit` | Unit for the contract amount |
| `contract_amount` | Approved contract amount (input — not a paid net) |
| `attendance_minutes` | Reserved; **live attendance not packaged yet** |
| `leave_classification` | Reserved; **live leave not packaged yet** |
| `period_start` / `period_end` | Pay period dates |

## Vendor result (upload back)

| Column | Meaning |
|---|---|
| `employee_key` | Must match the package |
| `component_code` | Must match a packaged component |
| `opaque_amount` | Vendor amount for **mirror review only** |
| `currency` | Currency code |
| `external_run_id` | Stable id for this vendor run (idempotency) |

## Not in package yet

Attendance minutes, leave classifications, shifts, bank/WPS files, PIFSS remittance, payment execution.
