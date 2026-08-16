# Super Admin Tenant Control — Wave 4 Onboarding, Activation & Final Qualification

**Date:** 2026-07-27  
**Scope:** Super Admin onboarding experience, deliberate delivery-sweep repair, bounded runtime cutover, synthetic qualification  
**Environment:** Production (`WATHEFNI` only)  
**Evidence run:** `20260727T112334Z` (`/tmp/wave4-tenant-control-20260727T112334Z/`)  
**Local evidence:** `ops/evidence/wave4-tenant-control/`  
**Backups:** `/opt/wathefni/var/wave4-backups/20260727T111240Z` (sweep), `/opt/wathefni/var/wave4-backups/20260727T112025Z` (code/UI)

## Verdict

**Technical PASS.**  
**GO/NO-GO for first real external company: NO-GO.**

Wave 4 delivers the Super Admin wizard and permanent company control page, repairs
the production delivery sweep deliberately, runs bounded WATHEFNI runtime-cutover
canaries with rollback, and qualifies a non-externally-usable synthetic tenant
lifecycle — without enabling an external `companies` row, without redesigning the
normal HR workspace, and without turning on global canonical authority.

First real external-company onboarding still requires explicit product
authorization plus the remaining platform-operation dependencies listed below.

---

## Non-negotiables preserved

| Constraint | Result |
|---|---|
| No external tenant in `companies` | Met — count = **1** (`WATHEFNI`) |
| No normal HR workspace redesign | Met — changes confined to Setup Console V2 |
| Global canonical authority | Hard-off |
| Real external messages during qualify | None — dry-run overlay during proofs |
| WATHEFNI suspension | Not performed; synthetic only |
| Orphan settings | **12** unchanged |
| Health | **200** throughout |
| Interviews ≠ video interviews | Both enabled and distinct |

---

## 1. Delivery-sweep deliberate repair

### Before

- Unit `wathefni-delivery-sweep.service` failed every timer tick
- Missing `WATHEFNI_ENV` / DB identity bindings → `application_environment_missing_or_invalid`
- Incorrect Wave 2 name `*-worker` does not exist; real unit is `wathefni-delivery-sweep`

### Repair applied

Production unit now includes:

- `WATHEFNI_ENV=production`
- `WATHEFNI_EXPECTED_DATABASE_HOST/PORT/NAME`
- `WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1`
- Existing workspace + postgres env + gog keyring
- Timer cadence unchanged (`OnUnitActiveSec=5min`)

Repo source of truth: `wathefni-orchestrator/ops/wathefni-delivery-sweep.service`

### Qualification (no real sends)

1. Temporary drop-in `wave4-qualify-dry-run.conf` set `WATHEFNI_DELIVERY_MODE=dry_run`
2. Manual + systemd runs returned `{"ok": true, "processed": 0, "skipped": 0}`
3. Epoch / lifecycle / integration gates remain inside `run_delivery_sweep` and `deliver_to_employee`
4. Dry-run overlay **removed** after proofs (rollback of qualify overlay)
5. Post-repair live unit: `Result=success`, `ExecMainStatus=0`, timer **active**, still `processed: 0` (no pending rows)

| Proof | Result |
|---|---|
| Binding identity | pass |
| Timer preserved | pass |
| Side-effect gates present | pass |
| Idempotent empty pass | pass |
| Qualify dry-run → restore live unit | pass |
| Real external messages during qualify | none |

---

## 2. Final onboarding information architecture

Setup Console V2 (`/setup-console`) now exposes three operator surfaces:

1. **Classic setup** (existing cards — kept compatible)
2. **Onboarding wizard** (10 steps)
3. **Company control** (permanent control page)

### Wizard steps

| # | EN | AR |
|---|---|---|
| 1 | Company | الشركة |
| 2 | Purchased modules | الوحدات المشتراة |
| 3 | Company structure | هيكل الشركة |
| 4 | Administrators and roles | المسؤولون والأدوار |
| 5 | Module configuration | إعداد الوحدات |
| 6 | Policies and workflows | السياسات وسير العمل |
| 7 | Integrations | التكاملات |
| 8 | Data and imports | البيانات والاستيراد |
| 9 | Readiness | الجاهزية |
| 10 | Review and activate | المراجعة والتفعيل |

### Wizard rules enforced

- Autosaved drafts (`tc_onboarding_wizard_drafts`) with session resume key
- Progress indicator + step chips
- Dependency explanations on module cards
- Selecting modules **never** sets live (`modules_live` forced empty)
- Candidate Knowledge / Talent Pool **excluded** from purchasable modules
- Unsupported providers shown as **Unavailable** (not “coming soon”)
- Blockers + remediation on validate
- EN/AR copy + `dir=rtl|ltr`

### Evidence of every wizard step

Structured step evidence HTML:

- Production: `/tmp/wave4-tenant-control-20260727T112334Z/wizard-steps-evidence.html`
- Local: `ops/evidence/wave4-tenant-control/wizard-steps-evidence.html`

All 10 steps validated successfully in the qualification run for the WATHEFNI draft.

UI code:

- `apps/wathefni-dashboard/src/setup-console/OnboardingWizard.tsx`
- Deployed dist: `/opt/wathefni/apps/wathefni-dashboard/dist/setup-console.html` (HTTP 200)

---

## 3. Permanent company control-page design

**Component:** `CompanyControlPage.tsx`  
**API:** `GET /dashboard/superadmin/setup/companies/{code}/control`

### Sections

Overview · Modules · Integrations · Roles and permissions · Policies · Data and imports · Readiness · Health · Audit history

### Module state vocabulary shown

`purchased` · `setup required` · `configured` · `testing` · `ready` · `live` · `paused` · `degraded` · `blocked`

### Operator clarity

- What works / incomplete / broken via badges + readiness blockers
- What requires action via remediation text
- What publish/pause would change via **impact preview** (navigation, APIs, mobile, AI tools, workers, timers, queued work, webhooks, intake, integrations, notifications, dependents)

Actions available: pause / resume (activate path requires readiness).

---

## 4. Runtime cutover matrix (WATHEFNI canaries only)

**Code:** `tenant_control_runtime.py`  
Global canonical authority remains hard-off. Cutover requires token
`WATHEFNI_TENANT_CONTROL_CUTOVER_TOKEN`.

| Boundary | Parity | Canary canonical | Rollback to legacy |
|---|---|---|---|
| `company_profile` | pass | pass | pass |
| `module_policies` | pass | pass | pass |
| `prehire_policies` | pass | pass | pass |
| `notification_policies` | pass | pass | pass |
| `supported_integration_state` | pass | pass | pass |
| `readiness_state` | pass | pass | pass |
| `roles_permissions_canary` | pass | pass | pass |
| `lifecycle_activation_epochs` | pass | pass | pass |

**8/8 boundaries** activated then rolled back. No global replacement of legacy reads.

Legacy dual-write retained. Outside approved canary boundaries, authority stays legacy.

---

## 5. Module / roles / integrations / readiness UX

| Area | Delivered |
|---|---|
| Module lifecycle API | configure/validate/test/review/publish remain Wave 3; pause/resume/activate + impact preview in Wave 4 |
| Commercial silent enable | Forbidden — readiness required for activate |
| Roles UX | Control-page section; fixed-role WATHEFNI behavior unchanged; role count canary only |
| Integration UX | Control-page shows state, tier, verification, kill switch; unsupported remain unavailable |
| Readiness | Grouped checks, blockers, evidence, expiry, remediation, retest (Wave 3 catalog + control page) |
| Imports | Dry-run batches with mapping/validation/duplicate/preview (`tc_import_batches`) |
| Offboarding | Preview only for WATHEFNI (suspension protected); hold/cancel choices; no drain by default |

Unsupported providers remain unavailable:

- Microsoft 365 / Outlook
- Microsoft Teams
- IMAP
- SMS

---

## 6. Synthetic tenant lifecycle results

Synthetic code: `__TC_WAVE4_SYNTHETIC__`

| Step | Result |
|---|---|
| Create control-plane tenant | pass (`synthetic=true`, `externally_usable=false`) |
| Purchase/configure modules only | pass (`live=false`) |
| Selected ≠ ready/live | pass (readiness not ready) |
| Suspend / restore / archive | pass (control-plane only) |
| Present in `companies` | **no** |
| Cross-tenant / external enable | none |
| WATHEFNI mutated by synth path | no companies/lifecycle change for WATHEFNI beyond approved canaries restored |

---

## 7. WATHEFNI parity / final proof

| Check | Result |
|---|---|
| Companies count | 1 |
| Orphan settings | 12 |
| Interviews enabled | true |
| Video interviews enabled | true |
| Distinct modules | true |
| False denials on live modules | none |
| Global authority | false |
| Delivery sweep healthy after repair | success / timer active |
| Setup Console V2 | enabled; `/setup-console` 200 |
| Unified inbound CV | frozen posture preserved (systemd drop-ins unchanged by this wave) |
| Verified-binding ENFORCE | remains WATHEFNI-scoped via existing production drop-ins |

---

## 8. Remaining platform-operation dependencies

Before the first real external company:

1. Explicit product authorization to create an externally usable `companies` row
2. Runtime cutover promotion plan beyond WATHEFNI canaries (still dual-write / legacy default)
3. Full end-to-end wizard activation against a sandbox company (not synthetic-only)
4. Partial providers completion (Gmail live import authority, Calendar self-serve, Push/employee app)
5. Custom-role parity canary with real grant matrix before replacing fixed roles
6. Monitoring window + automatic rollback recommendation wiring for activation health failures
7. Operator runbook for secret rotation / uninstall outside env-file locators
8. Confirm verified-binding and unified-inbound allowlists remain WATHEFNI-only when first external tenant is considered

---

## 9. Rollback proof

| Asset | Rollback |
|---|---|
| Delivery-sweep unit | `/opt/wathefni/var/wave4-backups/20260727T111240Z/delivery-sweep/*.pre` |
| Qualify dry-run overlay | Removed after proofs (proven) |
| Orchestrator code | `/opt/wathefni/var/wave4-backups/20260727T112025Z/pre/` |
| Dashboard dist | `/opt/wathefni/var/wave4-backups/<stamp>/dashboard-dist-pre/` |
| Runtime cutover | `POST .../cutover/rollback/{boundary}` (8/8 proven) |
| Module pause | resume canary proven |
| Decision/plane kill switches | unchanged Wave 2/3 switches |
| Global authority | remains forced off |

---

## 10. Code artifacts

| Path | Role |
|---|---|
| `tenant_control_wave4_schema.py` | Wizard/cutover/import/offboarding tables |
| `tenant_control_wizard.py` | Wizard + control snapshot + imports + offboarding preview |
| `tenant_control_runtime.py` | Bounded runtime cutover |
| `tenant_control_wave4_routes.py` | Super Admin APIs |
| `ops/wave4-tenant-control-onboarding-activation-qualification.py` | Production qualification |
| `ops/wathefni-delivery-sweep.service` | Repaired unit source |
| `apps/wathefni-dashboard/src/setup-console/OnboardingWizard.tsx` | Wizard UI |
| `apps/wathefni-dashboard/src/setup-console/CompanyControlPage.tsx` | Control page UI |
| `SetupConsoleApp.tsx` / `api.ts` | Integration + EN/AR toggle |

---

## 11. Final PASS/FAIL and GO/NO-GO

### Final qualification

**PASS** (`ok: true`, `failures: []`, evidence `20260727T112334Z`)

### GO/NO-GO for onboarding the first real external company

**NO-GO.**

Technical Wave 4 foundations are in place and proven on WATHEFNI + synthetic
control-plane records. Creating or enabling a real external company remains
blocked until product ownership explicitly authorizes it and the remaining
platform-operation dependencies above are closed.
