# Onboarding Wave 2 — Controlled template, backfill prep & staging mutation

**Stamp:** `20260802T010724Z`  
**Evidence:** `ops/evidence/onboarding-wave2-staging-20260802T010724Z/`  
**Scope:** Local + **staging only** (production code/flags/checklists untouched)

---

## Verdict

| Gate | Result |
|---|---|
| Wave 2 staging operational completeness | **PASS** (`31/31` synthetic smoke) |
| Wave 1 read-path regression (staging) | **PASS** `38/38` |
| E360 freeze (local) | **PASS** `54/54` |
| Production four-real checklists | **Unchanged** (no apply) |
| Production SEED / HR_MUTATE | **Remain off** |
| Staging SEED / HR_MUTATE | **on** (staging-only drop-in) |
| **WATHEFNI-only production synthetic canary** | **GO** (code deploy + synthetic-only; SEED/HR_MUTATE still gated; **no** real checklist migration) |
| Production real backfill / SEED-on-reals | **NO-GO** |

---

## Canonical template & versioning

**Module:** `wathefni-orchestrator/onboarding_wave2.py`

| Field | Value |
|---|---|
| Template id | `default_kuwait` |
| Version | **`2.0.0`** |
| Item count | **36** |
| Bank | `bank_details` with `authority=ess`, `collection_mode=ess_encrypted` (no plaintext) |
| Compliance | `*_expiry` rows are `authority=compliance_mirror` prompts; Compliance module remains source of truth |
| Due dates | `due_offset_days` relative to `planned_start_date` |
| Dependencies | e.g. `residence→civil_id`, `work_permit→residence`, `first_day_checklist→{employment_contract,civil_id,personal_photo}` |

**Version pin:** `employee_onboarding_assignments(template_id, template_version)` + `employees.onboarding_template_version` + per-item `template_version`. Historical assignments do **not** silently rewrite when the in-code template evolves.

---

## State & transition model

States: `not_started` → `delayed` / `in_progress` → `completed` | `cancelled` | `abandoned`

| Action | Behavior |
|---|---|
| `start_onboarding` | Duplicate-safe; optional `delayed` + future `planned_start_date` |
| `activate_delayed_starts` | Promotes `delayed` when start date reached |
| `reschedule_onboarding_start` | Updates planned start; recomputes open-item due dates; optimistic assignment version |
| `cancel_onboarding` | Terminal; **history preserved**; open items → `cancelled_onboarding` |
| Lifecycle abandon | Still maps to `abandoned` / `abandoned_employment_ended` |
| Mark / waive | `row_version` optimistic lock + dependency gate + `onboarding_audit_events` |

---

## Migration / backfill plan (four reals — **not applied**)

See `data/MIGRATION_PLAN.md` and `data/migration-plan.json`.

| Employee | Live | Missing vs v2 | Obsolete | Notes |
|---|---|---|---|---|
| Talal | 6 legacy | ~30+ | `education_cert`, `medical` | Preserve pending; bank→ESS mode |
| Fouad | 6 legacy | ~30+ | same | Preserve reminder counts |
| Mohammad | 6 legacy | ~30+ | same | Preserve `civil_id`/`bank_details` received |
| Brian | 1 (`personal_photo`) | nearly full template | — | **Explicit partial** — insert missing, never wipe photo |

**Rules:** preserve received + reminders; retire obsolete only via audited migration; **`apply_to_production: false`**.

---

## Staging flags & evidence

| Env | SEED | HR_MUTATE | App |
|---|---|---|---|
| Staging | **on** (`zz-onboarding-wave2-staging.conf`) | **on** | **off** |
| Production | **off** | unset/off | Talal allowlist only (unchanged) |

| Proof | Result |
|---|---|
| Wave 2 smoke | **31/31** (`tests/w2-smoke.txt`) |
| Wave 1 smoke | **38/38** (`tests/w2-w1.txt`) |
| E360 freeze local | **54/54** |
| Prod SHA | still Wave 1B `a73ee60b…` — no Wave 2 deploy |
| Staging SHA | Wave 2 `247a403d…` |

---

## Remaining risks

1. Production still on Wave 1B until a separate canary deploy of Wave 2 code  
2. Real checklist migration not yet executed anywhere (by design)  
3. ESS bank allowlist still empty — ESS handoff item tracks completion but real bank collection remains gated  
4. Dashboard UI not redesigned for delayed/cancel/version fields (API/backend ready)  
5. `cancelled` / `delayed` directory filters may need UI labels in a later polish wave  

---

## GO / NO-GO

**GO** for a **WATHEFNI-only production synthetic canary** of Wave 2 code:
- Deploy Wave 2 modules to production with **SEED=off / HR_MUTATE=off** by default  
- Enable mutations only for an explicit synthetic company/keys  
- Do **not** migrate the four real checklists in that canary  

**NO-GO** for production SEED-on-reals, HR_MUTATE-on-reals, or applying the four-real backfill until a dedicated controlled migration wave with backup + dual-control approval.
