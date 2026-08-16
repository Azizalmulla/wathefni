# Employees 360 Wave 5 — Employee & manager self-service (local/staging)

**Stamp:** `20260801T222932Z`  
**Evidence:** `ops/evidence/employees360-wave5-selfservice-local-20260801T222932Z/`  
**Schema:** `employees360-wave5-selfservice-v1`  
**Mode:** Local implementation + **staging** qualification  
**Production deploy:** **NOT DONE**  
**Real-employee lifecycle:** **NOT ENABLED**  
**UI redesign / Wave 6 / pre-hiring / Wave D:** **UNTOUCHED**

---

## Verdict

| Gate | Result |
|---|---|
| Architecture + request authority | **PASS** |
| Staging smoke | **41/41 PASS** |
| Staging flags + 9 ESS routes | **PASS** (`ESS_V5=on`, unauth policy **401**) |
| Prod untouched | **PASS** (no module / no `ESS_V5`) |
| Overall Wave 5 staging | **PASS** |

---

## Architecture

```
Employee / Manager / HR
        │
        ▼
  employee_ess_requests   ◄── versioned request authority
        │                   (proposed_values, old_value_snapshot,
        │                    approval_route, comments, concurrency_version,
        │                    audit events, applied_authority_ref)
        │
   decide (approve/reject/RFI)     apply (separate)
        │                             │
        ▼                             ▼
   state machine only          ESS overlays OR Wave 4
                               (never direct hub/lifecycle/
                                payroll authority edits)
```

**Canonical mutation policy**

| Domain | Write target on apply |
|---|---|
| Personal / emergency | `employee_ess_personal_profiles` overlay |
| Bank | `employee_ess_bank_profiles` (encrypted/cipher blob + fingerprint) |
| Documents | `employee_ess_document_versions` (prior versions retained as `replaced`) |
| Letters / service certificate | `employee_ess_letter_orders` (pending fulfillment) |
| Transfer / manager / assignment correction | **Wave 4** `apply_assignment_change` (effective-dated history) |
| Lifecycle / jurisdiction | **Not mutated** — remain Wave 3 governed |

**Module:** `wathefni-orchestrator/employee_selfservice_wave5.py`  
**Flags:** `WATHEFNI_EMPLOYEE_ESS_V5=on`, `WATHEFNI_EMPLOYEE_ESS_V5_COMPANIES=WATHEFNI`  
**Staging EnvironmentFile:** `/opt/wathefni/staging/var/employees360-wave5.env`  
**Drop-in:** `wathefni-orchestrator-staging.service.d/employees360-wave5.conf`

---

## Request types

### Employee-originated
- `personal_detail_change`
- `emergency_contact_change`
- `bank_detail_change`
- `document_change`
- `employment_letter`
- `service_certificate`

### Manager-originated
- `transfer`
- `manager_change`
- `assignment_correction`

---

## States

`draft` → `submitted` / routed → `needs_information` | `pending_manager` | `pending_hr` | `pending_payroll` → `approved` → `applied`  
Also: `rejected`, `withdrawn`, `failed` (e.g. stale apply).

**Rules enforced:** approval ≠ apply · no self-approval · apply idempotent · stale hub `updated_at` fail-closed · bank requires payroll stage · documents versioned · managers scoped · sensitive fields masked.

---

## Routing / permission matrix

| Request type | Approval route | Apply target |
|---|---|---|
| personal / emergency | `hr` | ESS personal overlay |
| bank_detail_change | `hr` → `payroll` | ESS bank overlay |
| document_change | `hr` | ESS document versions |
| employment_letter / service_certificate | `hr` | ESS letter orders |
| transfer / manager_change / assignment_correction | `hr` | Wave 4 history |

| Permission | Use |
|---|---|
| `employees.ess.request` | create / submit / withdraw |
| `employees.ess.approve.manager` | `pending_manager` |
| `employees.ess.approve.hr` | `pending_hr` |
| `employees.ess.approve.payroll` | `pending_payroll` |
| `employees.ess.apply` | approved → applied |
| `employees.ess.unmask` | unmasked sensitive fields |
| `employees.manage` / `employees.read` | HR fallbacks |

**Eligibility**

| Status | Behavior |
|---|---|
| active | all types (by requester kind) |
| future_start | personal/emergency/docs/letters OK; bank + assignment types blocked |
| suspended | personal/emergency/docs/letters OK; assignment/bank blocked |
| terminated | letters / service_certificate only |

---

## Staging proof (41/41)

Proved:

- Own-data + manager-scope isolation  
- Routing: personal → HR; bank → HR→Payroll; assignment → HR→Wave 4  
- RFI → resubmit; draft withdraw  
- Approve then separate canonical apply (idempotent)  
- Stale conflict, self-approval, cross-tenant denial  
- Assignment history preservation (prior slice closed)  
- Document v1→v2 with prior retained  
- Field-level IBAN masking  
- Future-start / suspended / terminated explicit behavior  
- Hub employee name unchanged after personal apply (overlay only)  
- `SYNTHETIC_ONLY` retained  

Artifacts: `remote/smoke-run.log`, `remote/smoke-rc.txt`, `remote/http-policy-unauth.txt` (401).

---

## API surface (staging)

```
GET  /dashboard/posthire/employee-ess/policy
GET  /dashboard/posthire/employee-ess/me/{employee_key}
GET  /dashboard/posthire/employee-ess/reports
GET  /dashboard/posthire/employee-ess/requests
POST /dashboard/posthire/employee-ess/requests
GET  /dashboard/posthire/employee-ess/requests/{request_id}
POST .../submit | /withdraw | /decide | /apply
```

---

## Risks

| Risk | Mitigation / residual |
|---|---|
| ESS overlays diverge from hub roster fields | Intentional; hub remains Wave 2/roster authority until a future sync wave |
| Bank cipher uses encrypt helper or staging plaintext_dev_only fallback | Production must require encrypt path before go-live |
| Manager reports depend on Wave 4 history + Wave 2 fallback | Requires ORG_V4 + AUTHORITY_V2 (already on staging) |
| Dashboard `actor_employee_key` passed explicitly for ESS identity | Needs employee-app binding before end-user rollout |
| Letter orders are pending stubs | Fulfillment / PDF generation is out of Wave 5 scope |
| Permission grants not yet role-defaulted | Explicit grants / manage fallback used in staging |

---

## Boundary checklist

| Constraint | Status |
|---|---|
| Local/staging only | **Yes** |
| No production deploy | **Yes** |
| No real lifecycle enablement | **Yes** |
| No UI redesign | **Yes** |
| No Wave 6 | **Yes** |
| No pre-hiring / Wave D changes | **Yes** |
| No direct canonical employment/lifecycle/payroll edits | **Yes** |
