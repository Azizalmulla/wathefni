# Employee Payslips P0 — HR Release Gate + Employee Read-Only

**Company:** WATHEFNI canary  
**Scope:** Extend HR Payroll Wave 3 with explicit employee release; Employee App self-scoped read-only  
**Out of scope:** Auth Wave 2 Phase 6 · broader P1 Employee App roadmap · official PDF / payment processing

## Verdict

See latest stamp under `ops/evidence/employee-payslips-p0-*/results.json`.

## Authority model (canonical)

Document lifecycle (unchanged): `status ∈ {active, replaced, revoked}`

**Orthogonal release gate** on `payroll_payslip_documents`:

| Field | Values |
|---|---|
| `employee_visibility` | `not_released` (default) · `released` |
| `employee_released_at` / `employee_released_by_phone` / `employee_release_note` | audit |

**Employee App may show a payslip iff**

`status = active` **AND** `employee_visibility = released`

| HR `employee_facing_state` | Meaning |
|---|---|
| `not_released` | Active doc, hidden from employee |
| `released` | Active + released → employee-visible |
| `replaced` | Superseded; not employee-visible |
| `revoked` | Revoked; not employee-visible |

**Never infer visibility from** period `open|locked|closed`.

### Semantics

1. Generate → `active` + `not_released` (never auto-visible)
2. Release → deliberate, idempotent; may notify once (`payslip_ready`)
3. Unrelease → withdraw app visibility; document stays active for HR
4. Replace → prior `replaced`; new version starts `not_released` (must re-release)
5. Revoke → not employee-visible; history retained

## Employee API

| Route | Gate |
|---|---|
| `GET /app/payslips` | feature `payslips` + wave3 company + released only |
| `GET /app/payslips/{id}` | same + self employee_key |
| `GET /app/payslips/{id}/download` | same + `download` action → statement `.txt` |

Never exposes other employees, drafts, approval workflow, calc debug, unreleased/revoked.

## Download honesty / blockers to official PDF

- Download = employee-safe **statement summary** `.txt` with honesty banner
- `official_document=false` · `X-Wathefni-Official-Document: false`
- `payment_date` always `null` (never invented)
- Native slips remain `money_authority=preview_non_authoritative`

**Blockers before official downloadable payslips:**

1. Official PDF generation + signed storage
2. Authoritative money source for native (or release external-only)
3. Real payment confirmation / `payment_date` field
4. Production non-synthetic payroll authority (Wave 3 still synthetic-only in prod)

## Module entitlements

`payslips` feature depends on company `payroll` module (`implemented: true`).  
If payroll off → no nav / Home card / API (403 feature disabled). Adaptive: Profile/Home entry only when enabled (no permanent empty tab).

## Notifications

Successful non-idempotent release → `employee_messages` `flow=payroll` `template=payslip_ready` with deep link `/payslips?payslip_id=…`. No notify on drafts/unreleased replacements.

## Prove matrix

| Case | Expected |
|---|---|
| Draft/unreleased | Invisible to employee |
| Explicit release | Visible to that employee only |
| Peer access | 404 |
| Unrelease / revoke | Unavailable |
| Replace | Latest needs re-release; history kept |
| Duplicate release | Idempotent |
| Payroll module off | Feature disabled |
| EN/AR | Catalog + honesty localized |

Smoke: `ops/smoke-test-employee-payslips-p0.py`
