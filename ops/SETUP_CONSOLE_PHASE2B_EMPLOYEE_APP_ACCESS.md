# Setup Console Phase 2B — Employee App Access Mode UI

**Status:** PASS (canary qualified) · **Frozen**  
**Depends on:** Phase 1 ownership · Phase 2A payroll setup · existing Employee App eligibility/invite architecture  
**Do not auto-start:** Phase 2C · Employee App P1 · Auth Wave 2 Phase 6

## Verdict

**PASS** — canary live smoke **29/0**

Evidence: `ops/evidence/setup-console-phase2b-20260808T022409Z`  
Canary: `/opt/wathefni/ops/evidence/setup-console-phase2b-20260808T022409Z`

Smoke: `wathefni-orchestrator/smoke-test-setup-console-phase2b.py`

## Final access-policy semantics

| Layer | Truth |
|---|---|
| Module OFF (Setup → Modules) | Zero access, zero invites, no employee-app surfaces |
| Runtime invite / entry | Module ON ∧ employment active ∧ `employees.app_access_enabled` |
| Durable who-can-use policy | `company_modules.employee_app.settings` (`access_mode`, `selection_scope`, `selected_departments`, `selected_employee_keys`, product `ux_mode`) |
| Module entitlements | Separate — what surfaces appear **inside** the app once access is granted |

### Who should have access?

| UX (Setup) | Storage | Future hire |
|---|---|---|
| Everyone | `access_mode=all` | Auto-eligible when an active employee is created / reconciled |
| Specific departments | `access_mode=selected`, `selection_scope=departments`, `selected_departments[]` | Auto-eligible when active employee’s department is in scope |
| Specific employees | `access_mode=selected`, `selection_scope=employees`, `selected_employee_keys[]` | **No** automatic access — HR must select |

Apply is a durable policy + reconcile (not a one-shot bulk toggle):

1. Preview gain / lose / unchanged / sessions / pending invites  
2. Large removals (≥10) require confirm  
3. Persist settings  
4. Batch `UPDATE` flags (not N+1 UI writes)  
5. Existing invite path for newly enabled (idempotent)  
6. Existing revoke / supersede pending invites for removals — no account/data deletion  

Imports/migrations never invite by themselves (`allow_invite=False` on migration org changes; flag-only enable when needed).

## Reconciliation architecture

```
Setup Console apply_access_policy
  → persist durable settings
  → desired vs current flags (previewed first)
  → batch UPDATE app_access_enabled
  → invite only newly enabled (existing invitation delivery; idempotent)
  → revoke sessions + supersede pending invites for newly disabled

Dashboard roster create → reconcile(allow_invite=True) against durable policy
Hub department edit → reconcile(allow_invite=True)
Org assignment change → sync hub profile.department + reconcile
  change_type=migration → allow_invite=False
```

Department moves (e.g. Sales → Finance under Department mode) re-evaluate against current canonical department policy — not only the original save event.

## Setup Console UX

`#classic-app-access` · EN/AR · RTL · authorized Setup operators only · audited applies

1. Module on/off remains Modules (not duplicated here)  
2. Who should have access? — Everyone / Specific departments / Specific employees  
3. Departments — multi-select + affected counts  
4. Employees — searchable bulk roster select (not per-profile navigation)  
5. Preview impact → confirm large removals → Apply with audit reason  
6. Day-to-day per-employee status stays in Employees / Employee 360  

Access mode ≠ module entitlements (called out in card copy).

## Qualification coverage

| Scenario | Evidence |
|---|---|
| Module OFF blocks desired access | `desired_module_off_blocks` |
| Everyone / departments / employees desired-state | unit PASS |
| Future hire Everyone / Dept / Selected | unit PASS |
| Preview + employee search live | live PASS |
| Apply selected + idempotent re-apply | live PASS |
| Batch flags + invite trigger + migration no-invite | source PASS |
| Tenant isolation | `live_tenant_404` |
| UI EN/AR modes + no internal jargon | UI PASS |

## Remaining Phase 2C gaps (do not start)

~~1–3 (org-unit IDs, drill-down, 10k picker)~~ → completed in Phase 2C — see `ops/SETUP_CONSOLE_PHASE2C_EMPLOYEE_APP_ACCESS.md`  
4. Cross-company access templates  
5. Employee App shell composition from access + entitlements (Phase 5)  

## Key files

- `wathefni-orchestrator/employee_app_access.py` — policy, preview, apply, reconcile  
- Setup routes in `app.py` — GET/PATCH/preview/employees  
- `employee_org_wave4.py` — post-assignment reconcile (migration-safe)  
- `apps/wathefni-dashboard/src/setup-console/EmployeeAppAccessPolicyCard.tsx`  
- `apps/wathefni-dashboard/src/setup-console/api.ts`  
