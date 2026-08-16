# R6 configuration ownership matrix

Rule: customer-facing policy → Setup. Environment → secrets, infrastructure, kill switches, staged allowlists.

| Capability | Customer policy authority | Setup surface | Runtime consumer | Env / infra role |
|---|---|---|---|---|
| Catalog modules (Leave, Attendance, Onboarding, Payroll, Performance, Talent, Learning, Benefits, ER, Engagement, Comp, WFP, Employee App, Analytics) | `company_modules` + domain settings | What this company uses + module cards | Each domain gate | Kill switch / empty-allowlist invert |
| Job Architecture | `ja_company_settings` | `#classic-wave6-job-architecture` | C1 | Class A kill switch. **Platform foundation, not a SKU** |
| Compensation Planning | `cp_company_settings` | `#classic-wave6-comp-planning` | C6 | Class A + **company JA required** |
| Workforce Planning | `wfp_company_settings` | `#classic-wave6-workforce-planning` | C7 | Class A + **company JA required** |
| HR Intelligence | `hr_intelligence_c1_company_settings` + C6 surfaces | `#classic-wave5-hr-intelligence` | Frozen C1 evaluator / C6 surfaces | Class A C1 flag + analytics kill + staged allowlist |
| Leave policy | `leave_policies` | Module Leave card + Wave 2 leave card (same store) | Frozen Leave domain | None for customer policy |
| Attendance ops | `company_modules.settings.attendance_setup` | Module Attendance card | Attendance ops | None |
| Attendance ingest | `wave2_setup.attendance` | Wave 2 attendance card | Wave 2 ingest | None |
| Attendance pay mode | Payroll Setup / `payroll_company_policy_versions` | Payroll Setup | Payroll | None |
| Onboarding auto-start | `company_settings.onboarding.auto_start_on_hire` | Wave 1 auto-start + onboarding overlay write-through | Wave 1 hire start | `WATHEFNI_ONBOARDING_SEED` infrastructure only |
| Notification preset | `company_settings.notification_preset` | `#classic-notifications-delivery` | Delivery layer | Push flag / provider secrets stay env |
| Channels | Existing channel policy cards | Setup channel cards | Outbound layer | Provider credentials stay integrations |
| Employee App company entitlement | `company_modules.employee_app` + access card | Employee App Access card | Employee App | Master kill + employee-key allowlists stay Class A |

Multiple UI cards may **read** the same authority. They must not maintain conflicting writes.
