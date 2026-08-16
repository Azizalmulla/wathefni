# Payroll Wave 2A-C — Staging Qualify Report

**Stamp:** `20260803T045904Z`  
**Evidence:** `ops/evidence/payroll-wave2ac-20260803T045904Z/`  
**Scope:** External payroll operations workflow (staging only)  
**Wave 2B:** not started

## Verdict

| Gate | Result |
|------|--------|
| Staging Wave 2A-C workflow | **GO** |
| Production synthetic qualification (2A-C-B) | **NO-GO** |

Staging GO for the HR-facing external payroll ops workflow around the frozen Wave 2A adapter.  
**NO-GO for production synthetic** until a dedicated Wave 2A-C-B prod synthetic path (deploy drop-in + canary + residual cleanup) is run — this wave explicitly did not deploy production.

## What shipped

### Backend (`payroll_external_adapter_wave2a.py` helpers — no Wave 2A DDL/contract changes)
- Period readiness + missing-input blockers
- Assemble period export inputs (manager-scope filter)
- List exports / imports / quarantine / events / import lines
- Reconciliation read + replace-import flow
- Workspace bootstrap with honesty envelope

### Dashboard APIs (`/dashboard/posthire/payroll/external/*`)
- Bootstrap, readiness, generate/download export
- Multipart upload + replace import
- Reconcile, quarantine, audit timeline, rollback
- Permission gates: `payroll.read` / `export` / `manage` / `approve`
- Manager scope via `manager_scope_employee_keys`
- Every mutation returns `authoritative_in_wathefni=false`, `money_authority=external`

### UI
- `ExternalPayrollWorkspace.tsx` + `payrollExternalUx.ts` (EN/AR)
- Payroll page tabs: External run | Timesheets
- Honesty strip, empty/loading/error/quarantine/reconciled surfaces
- Mobile-friendly stacked layout; RTL when `ar`

## Proofs (staging)

| Proof | Result |
|-------|--------|
| Wave 2A adapter regression smoke | 41/41 PASS |
| Wave 2A-C ops smoke | 34/34 PASS |
| Duplicate upload idempotent | PASS |
| Stale fingerprint → quarantine / block | PASS |
| Malformed → quarantine | PASS |
| Replace-import + audit event | PASS |
| Native mode readiness blocker | PASS |
| Manager empty scope → no employees | PASS |
| Import never Wathefni money authority | PASS |
| Honesty: `payment_processing=disabled`, `vendor_claimed=false` | PASS |
| Sibling freezes E360 / Onboarding / Attendance / Leave / Shifts | all green |

## Explicit holds (unchanged)

- `payment_processing=disabled`
- External remains money authority; imports are mirror-only
- `vendor_claimed=false` — no real vendor connection
- No native gross-to-net
- No bank files, PIFSS, WPS, EOS, journals
- No changes to frozen Wave 1 or Wave 2A contracts
- No AI assistant work
- No Wave 2B

## Production synthetic gate

**NO-GO** for `PROD_SYNTHETIC_PAYROLL_WAVE2AC_*` until Wave 2A-C-B:
1. Prod synthetic deploy of ops UI/API helpers (flags already on Wave 2A-B)
2. Prod canary for permission/scope + duplicate/stale fingerprint paths
3. Residual cleanup = 0
4. Sibling freezes re-confirmed on prod path

## Next

- Optional: Wave 2A-C-B production synthetic qualification for the ops workflow
- Do **not** start Wave 2B (native calculations)
