# R6 duplicate-policy resolution (R1 P1-18)

| Domain | Canonical store | Display cards | Non-authoritative / write-through | Proof |
|---|---|---|---|---|
| Leave | `leave_policies` (including `enforced`) | `#classic-module-leave`, `#classic-wave2-leave` | `company_modules.settings.leave_setup` optional overlays only. Wave 2 `enforced` → `leave_policies.enforced` | Staging D: Wave 2 write, both readers see `enforced=true` |
| Attendance ops | `company_modules.settings.attendance_setup` | `#classic-module-attendance` | Grace / clock-out / corrections live here only | Staging D: grace 11 from Setup overlay |
| Attendance ingest | `wave2_setup.attendance` | `#classic-wave2-attendance` | Different concern; not ops grace | Not rewritten |
| Attendance pay mode | Payroll Setup / `payroll_company_policy_versions` | `#classic-payroll-setup-attendance` | Do not invent a third pay-mode answer | Frozen Payroll authority |
| Onboarding auto-start | `company_settings.onboarding.auto_start_on_hire` | `#classic-wave1-onboarding-auto-start`, `#classic-module-onboarding` | `onboarding_setup.auto_seed_on_hire` write-through. `WATHEFNI_ONBOARDING_SEED` is infrastructure | Staging D: both cards share `auto_start_on_hire=false` |

`duplicate_stores_removed_or_non_authoritative=true`. Frozen Leave / Attendance / Onboarding domain math was not rewritten.
