# Super Admin Tenant Control — Wave 1 Foundation

**Date:** 2026-07-27  
**Scope:** Canonical tenant control-plane foundation only  
**Environment:** Production (`WATHEFNI` only)  
**Evidence run:** `20260727T022129Z` (`/tmp/wave1-tenant-control-20260727T022129Z/evidence.json`)

## Verdict

**GO for Wave 2.**

Wave 1 established an additive, shadow-only control plane around the live
WATHEFNI tenant without changing HR UI, without enabling external tenants, and
without flipping entitlement authority away from `company_modules`.

Priority 0 is closed: Setup Console bulk module saves can no longer disable the
live scheduled `interviews` capability when it is already enabled.

## Non-negotiables preserved

| Constraint | Result |
|---|---|
| No normal HR UI redesign | Met — Setup Console UI unchanged; backend write path only |
| No external tenants | Met — `companies` still exactly `WATHEFNI` |
| No change to live WATHEFNI entitlement behavior | Met — legacy reads still use `company_modules` / `require_entitlement` |
| Authoritative new-model decisions | Forced off (`authoritative_enabled()` always `False`) |
| Unified inbound CV freeze | Healthy — adapters/wave4/authority tenants remain `WATHEFNI` |
| Verified-binding ENFORCE | Active for `WATHEFNI` only; not global |
| Health | `200` before and after restart |

---

## 1. Priority 0 — `interviews` vs `video_interviews`

### Conflict

Checkout had drifted from production:

- production already listed `interviews` as a first-class catalog module;
- checkout lacked `interviews`, `LEGACY_IMPLIED_MODULES`, and
  `apply_legacy_module_implications`;
- Setup Console bulk save still did
  `UPDATE ... enabled=false ... module_key <> ALL(requested)`, so any payload
  omitting `interviews` would take scheduled interviews offline.

### Fix

1. Restored the production catalog contract in `module_catalog.py`:
   - `interviews` = live scheduled interviews
   - `video_interviews` = async recorded-answer interviews
   - independent hard deps on `pre_hiring` only
2. Added `SETUP_PROTECTED_COMPATIBILITY_MODULES = {"interviews"}`
3. Added `protect_setup_module_selection(requested, currently_enabled)`
4. Wired protection into `setup_console_set_modules` before dependency checks
   and before the disable-all-others update

### Proof

Omitting `interviews` from a save payload while it is currently enabled yields:

```text
protected_retained = ["interviews"]
result includes interviews
```

Live interview rows remain:

| status | count |
|---|---|
| scheduled | 2 |
| completed | 2 |

---

## 2. Canonical product / capability catalog

**Catalog version:** `tenant-control-catalog-v1`  
**Code:** `wathefni-orchestrator/tenant_control_catalog.py`

### Distinctions

| Kind | Purpose | Examples |
|---|---|---|
| `business_module` | Purchased commercial modules | `mod.pre_hiring`, `mod.interviews`, `mod.video_interviews` |
| `sub_capability` | Backend capability under an HR product area | `cap.candidate_knowledge`, `cap.talent_pool` |
| `hidden_technical` | Compatibility / pipeline internals | `cap.interviews_compatibility`, `cap.unified_inbound_cv`, `cap.verified_job_binding` |
| `ui_surface` / `api` / `worker` / `timer` / `webhook` / `notification` / `integration` | Surface inventory for shadow matrix | dashboard nav, require_entitlement, CK worker, outbound delivery, WhatsApp/Postmark/Gmail |

### Candidates product area rule

Candidate Knowledge and Talent Pool are **not** purchasable Setup Console
modules. They are backend capabilities under the single HR-facing Candidates
area (`mod.pre_hiring`).

### Commercial vs technical dependencies

- Technical deps may be granted internally (`implied_technical`).
- Commercial deps block publish and name the missing purchased module.
- Wave 1 proof: selecting `assessments` without `pre_hiring` blocks publish.

### Legacy module catalog (still live)

13 product modules in `module_catalog.py`:

`pre_hiring`, `assessments`, `interviews`, `video_interviews`,
`employment_offers`, `onboarding`, `compliance`, `attendance`, `shifts`,
`leave`, `payroll`, `analytics`, `employee_app`

---

## 3. Exact new schema (additive only)

**Schema version:** `tenant-control-schema-v1`  
**Code:** `wathefni-orchestrator/tenant_control_schema.py`

Created with `CREATE TABLE IF NOT EXISTS` only.  
**Not removed / not replaced:** `companies`, `company_modules`,
`company_settings`, or current entitlement reads.

| Table | Role |
|---|---|
| `tc_tenants` | Tenant identity + lifecycle shadow of `companies` |
| `tc_contract_entitlements` | Contracted capability entitlements |
| `tc_tenant_module_instances` | Per-tenant module instance state |
| `tc_tenant_capability_grants` | Purchased / technical / compatibility / flag grants |
| `tc_dependency_definitions` | Versioned dependency graph |
| `tc_tenant_config_versions` | Versioned config with before/after/diff + rollback target |
| `tc_configuration_drafts` | Draft records before publish |
| `tc_readiness_checks` | Readiness check results |
| `tc_activation_events` | Activation / import / rollback events |
| `tc_audit_events` | Mandatory audit persistence |
| `tc_outbox_events` | Mandatory outbox persistence |
| `tc_shadow_decision_runs` | Shadow legacy-vs-canonical comparisons |
| `tc_orphan_classifications` | Orphan classification ledger (no deletes) |
| `tc_control_plane_meta` | Schema/catalog meta |

---

## 4. Legacy → canonical mapping

| Legacy `company_modules.module_key` | Canonical capability |
|---|---|
| `pre_hiring` | `mod.pre_hiring` |
| `assessments` | `mod.assessments` |
| `interviews` | `mod.interviews` + `cap.interviews_compatibility` |
| `video_interviews` | `mod.video_interviews` |
| `employment_offers` | `mod.employment_offers` |
| `onboarding` | `mod.onboarding` |
| `compliance` | `mod.compliance` |
| `attendance` | `mod.attendance` |
| `shifts` | `mod.shifts` |
| `leave` | `mod.leave` |
| `payroll` | `mod.payroll` |
| `analytics` | `mod.analytics` |
| `employee_app` | `mod.employee_app` (flag-gated) |

Implied technical grants when `pre_hiring` is enabled:

- `cap.candidate_knowledge`
- `cap.talent_pool`
- `cap.unified_inbound_cv`
- `cap.verified_job_binding`

---

## 5. WATHEFNI imported state

| Field | Value |
|---|---|
| `tenant_id` | `d67c9ded-da3a-4684-ba3b-258186cac218` |
| lifecycle | `active` (shadow) |
| enabled modules imported | 12 / 12 — zero loss |
| commercial gaps | none |
| catalog version | `tenant-control-catalog-v1` |
| `tc_tenants` | 1 |
| enabled module instances | 12 |

Imported enabled modules (exact parity with legacy):

```text
analytics, assessments, attendance, compliance, employment_offers,
interviews, leave, onboarding, payroll, pre_hiring, shifts, video_interviews
```

`employee_app` remains absent/disabled in legacy and was not silently enabled.

---

## 6. Shadow decision service

**Code:** `tenant_control_service.run_shadow_matrix`  
**Mode:** shadow-only; never authoritative in Wave 1

Surfaces checked:

`navigation`, `direct_routes`, `apis`, `ai_tools`, `mobile`, `workers`,
`timers`, `queue_claims`, `webhooks`, `intake`, `outbound_notifications`

### Results (WATHEFNI)

| Metric | Value |
|---|---|
| Decisions checked | 143 |
| Mismatches | 0 |
| Parity | **true** |
| Legacy modules | 12 |
| Canonical modules | 12 |

Shadow rows persisted to `tc_shadow_decision_runs`.

---

## 7. Safe setup mutations / dual-write

Setup Console UI is unchanged. Writes now:

1. protect currently-enabled `interviews`
2. validate commercial + module dependencies (commercial gaps block publish)
3. mutate legacy `company_modules` as before
4. dual-write into control-plane draft/version/grant/audit/outbox tables
5. return `protected_retained`, `control_plane.version_number`, and
   `control_plane.rollback_target`

### Dual-write proof

Requested payload deliberately omitted `interviews`.

| Check | Result |
|---|---|
| Interviews retained | true |
| `protected_retained` | `["interviews"]` |
| Version created | 2 |
| Rollback target | 1 |
| Rollback proof | true |
| Legacy `company_modules` enabled count after proofs | still 12 |

Kill switches:

- `WATHEFNI_TENANT_CONTROL_PLANE` (master)
- `WATHEFNI_TENANT_CONTROL_DUAL_WRITE`
- `WATHEFNI_TENANT_CONTROL_SHADOW`
- `WATHEFNI_TENANT_CONTROL_AUTHORITATIVE` ignored / hard-forced false

---

## 8. Orphan-record classification

### 12 orphan `company_settings` rows

All retained. None deleted.

| company_code | classification | ownership | settings |
|---|---|---|---|
| ASSTJRPROD | test_seed | feature_canary_harness | `{}` |
| ASSTJRPROD2 | test_seed | feature_canary_harness | `{}` |
| ASSTPROD | test_seed | feature_canary_harness | `{}` |
| ASSTPROD2 | test_seed | feature_canary_harness | `{}` |
| OFFER1XO | test_seed | feature_canary_harness | `{}` |
| RANKPRESPROD | test_seed | feature_canary_harness | `{}` |
| RANKPRESPROD2 | test_seed | feature_canary_harness | `{}` |
| RANKPROD | test_seed | feature_canary_harness | `{}` |
| TENANTREADTESTA | test_seed | tenant_read_hardening_suite | `{}` |
| TENANTREADTESTB | test_seed | tenant_read_hardening_suite | `{}` |
| ZZSEED99D590A5 | test_seed | ops_seed_harness | `{}` |
| ZZSEEDA48392EB | test_seed | ops_seed_harness | `{}` |

Classifications also stored in `tc_orphan_classifications`.

### Other orphan probes

| Table | Orphan count |
|---|---|
| `company_modules` | 0 |
| `dashboard_users` | 0 |
| `positions` | 0 |
| `applications` | 0 |
| `employees` | 0 |
| `candidate_interviews` | 0 |

### Referential-integrity migration plan (do not execute in Wave 1)

1. Keep orphan `company_settings` rows immutable until Wave 2 cleanup ticket.
2. Add deferred FK / reporting view:
   `company_settings.company_code` → `companies.company_code` as
   **NOT VALID** / monitoring-only first.
3. Quarantine harness codes behind an allowlisted prefix registry
   (`ASST*`, `RANK*`, `OFFER*`, `TENANTREAD*`, `ZZSEED*`) so future seeds
   write to a dedicated harness schema or always clean up both
   `companies` and `company_settings`.
4. Before any delete: export orphan rows, confirm no dependent rows in
   modules/users/domain tables (already 0 for probed tables), then delete in
   a reversible transaction with outbox audit.
5. Wave 2 should add creation-time FK enforcement for new settings rows only.

---

## 9. Production integrity proofs

| Proof | Result |
|---|---|
| WATHEFNI legacy/new decision parity | PASS (143/143) |
| Zero module loss | PASS |
| Scheduled interviews functional posture | PASS (`interviews` enabled; 2 scheduled, 2 completed) |
| Navigation/API entitlement source unchanged | PASS (still `company_modules` / `require_entitlement`) |
| Workers/timers authority unchanged | PASS (no authoritative flip) |
| Unified inbound CV frozen/healthy | PASS |
| Verified-binding ENFORCE for WATHEFNI | PASS |
| ENFORCE not global | PASS |
| Health 200 | PASS |
| No external tenant access | PASS |
| Rollback + kill switch | PASS |

---

## 10. Code / deploy artifacts

| Path | Role |
|---|---|
| `wathefni-orchestrator/module_catalog.py` | Catalog + P0 protection |
| `wathefni-orchestrator/tenant_control_catalog.py` | Versioned capability catalog |
| `wathefni-orchestrator/tenant_control_schema.py` | Additive schema |
| `wathefni-orchestrator/tenant_control_service.py` | Import, dual-write, shadow, orphans |
| `wathefni-orchestrator/app.py` | Setup save protection + dual-write + ensure hook |
| `wathefni-orchestrator/ops/wave1-tenant-control-foundation.py` | Production proof runner |
| `wathefni-orchestrator/ops/patch-wave1-app-tenant-control.py` | Production app patch helper |
| `wathefni-orchestrator/smoke-test-tenant-control-wave1.py` | Local/unit smoke |
| `wathefni-orchestrator/smoke-test-module-catalog.py` | Updated for 13-module catalog |

Production backup before patch:

`/opt/wathefni/var/wave1-backups/20260727T021856Z`

---

## 11. Explicitly out of scope / still true after Wave 1

- Normal HR UI was not redesigned.
- External tenants were not enabled.
- New model is **not** authoritative for runtime entitlement.
- Workers/queues/webhooks still lack universal active-company gates (Wave 2).
- Company disable/archive is still not a full processing suspension (Wave 2).
- Orphans were classified, not deleted.

---

## 12. Final GO / NO-GO for Wave 2

### GO

Proceed to Wave 2 (universal enforcement and lifecycle safety) on top of this
foundation.

### NO-GO conditions that remain

Do not:

- enable an external tenant yet;
- set `WATHEFNI_TENANT_CONTROL_AUTHORITATIVE` (hard-disabled in code anyway);
- treat Setup Console “Ready” as proof a module is fully live across workers;
- delete orphan `company_settings` rows without the Wave 2 integrity ticket;
- rely on UI hiding alone for entitlement.

Wave 1 foundation is complete. Stop.
