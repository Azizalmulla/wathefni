# Residual register — interaction audit

**Base stamp:** `20260805T195406Z`  
**Late P0/P1 closure stamp:** `20260805T220256Z`  
**Assurance program open:** `20260806` (P0/P1 confirmed work closed; residual retained)

## Confirmed P0/P1 — CLOSED

There are **0** confirmed broken, dead, or permission-mismatched P0/P1 controls in the final matrix after late closure. Shipped fixes (see audit `QUALIFICATION.md`):

1. Talent pool classification authority + calm errors + audit  
2. Viewer intake gate  
3. Calm API error surfaces (dashboard/setup/posthire)  
4. Onboarding/leave a11y names  
5. DB pool canary capacity  
6. Static dead-control prebuild gate  
7. Attendance Ops `attendance.read` / `attendance.manage` + audit  
8. WhatsApp turn internal-token fail-closed  
9. Employee account deletion capability + idempotent HR task  
10. Onboarding upload capability gate  
11. Leave/notification repeat locks; Documents/Settings back  
12. Action-inbox deep links + RTL nav  
13. Soft-gate: empty permissions fail closed for Employees  

**Product development is not blocked on residual unproven/P2 work.**

## Suite count reconciliation (410 vs 415)

| Source | Files | Passed | Failed | Total |
|---|---|---|---|---|
| `dashboard-full-suite.out` (earlier) | 79 | **410** | 13 | 423 |
| `dashboard-broad-suite-late.out` | 80 | **415** | 13 | 428 |
| Current Vitest inventory | — | — | — | **428** |

Same 13 failure **names** in both runs. The +5 passed / +1 file delta is additional passing coverage (including interaction contract tests), not a silent drop of failures. `EmployeeProfile.repro` is not among the 13 (already green).

### 13 Vitest assertions — disposition

All 13 were **test drift after intentional UX**, not live product regressions:

| # | Test | Disposition |
|---|---|---|
| 1 | `App.test.tsx` compliance-only landing | FIX_TEST → assert Compliance (Employees soft-gated in nav) |
| 2–6 | `SetupConsoleApp.test.tsx` (5) | FIX_TEST → open **Classic setup** after company select |
| 7–9 | `SettingsEmailSending.test.tsx` (3) | FIX_TEST → open **Communications** tab |
| 10 | `InterviewsPage.test.tsx` | FIX_TEST → tolerate status tiles + tabs |
| 11 | `candidateProfilePresentation.test.ts` | FIX_TEST → stage `'—'` for Talent Pool |
| 12 | `EmployeesDirectoryContract.test.ts` | FIX_TEST → Migration & Sync entry |
| 13 | `PosthireMutationIntegrityContract.test.ts` | FIX_TEST → “Mark this item complete” |

## Open residual (tracked, non-blocking)

### A. 495 P1 `unproven` destructive properties

Not confirmed defects. Mostly destructive mutation / idempotency / audit properties that cannot be proven against live customer records.

| Evidence source | Count (approx.) |
|---|---|
| browser-postdeploy | 317 |
| static-mutation-route | 119 |
| browser-targeted-final | 48 |
| dashboard-role-api | 11 |

**Proof path:** progressive synthetic fixtures (`interaction_assurance_fixtures.py` + canary). Batches may pass/fail independently; incomplete coverage does **not** fail releases.

### B. Raw/unclear mutation error contracts (P2)

Originally **91** role-API rows with raw machine-code bodies on invalid fixtures, plus **1** suite row (resolved via Vitest fixes above).

Module order for calm-message waves:

1. **calendar** (2) — started  
2. employee-ess (4)  
3. employee-org / lifecycle  
4. attendance capture-ops  
5. prehire applications / interviews  
6. shifts / payroll (largest)

### C. Static normalizer candidates

7 frontend endpoint literals still need endpoint-specific proof before removal from the unmatched set.

## Evidence anchors

- Matrix: `ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/findings/interaction-control-matrix.{json,csv}`
- Qualification: `…/QUALIFICATION.md`
- Rollback: `…/deploy/ROLLBACK.sh`
