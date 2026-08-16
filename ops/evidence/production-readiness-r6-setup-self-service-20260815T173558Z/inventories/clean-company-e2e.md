# R6 clean-company no-developer E2E

Target: a company administrator configures a representative stack using only product/admin surfaces.

## What the harness did

Isolated tenants `R6AF1BAF5` / `R6BF1BAF5` were created for cleanup (SQL bootstrap of empty `companies` rows only). After bootstrap:

| Action | Path | Env / SQL / Python policy write? |
|---|---|---|
| Leave policy | `patch_leave_company_policy` | No |
| Attendance ops | `patch_attendance_company_policy` | No |
| Onboarding auto-start | `patch_wave1_onboarding_auto_start` | No |
| Notification preset | `patch_delivery_policy` | No |
| Intelligence enable + cohort + fiscal | `patch_wave5_module_policy` | No (`REGISTRY_COMPANIES` stayed empty) |
| JA enable | `enable_company_job_architecture` | No |
| Comp enable after JA | `patch_wave6_module_policy` | No |
| Company-admin GET/PATCH | `/dashboard/setup/company/module-policies*` | No |

Deployment flags used by the in-process test (`WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1=on`, empty allowlists, analytics kill off) are **infrastructure pre-provision**, not customer policy.

## Representative stack coverage

Employees / Onboarding / Attendance / Leave / Payroll / Performance / Talent / Intelligence / Job Architecture / Learning / Benefits / ER / Engagement / Compensation Planning / Workforce Planning are all Setup-owned for customer enablement after R5. R6 proved the remaining gaps: Intelligence policy, notification preset, Leave/Attendance/Onboarding convergence, and Comp/WFP JA dependency.

## Not required for customer policy

- Shell access
- SQL row edits after bootstrap
- Environment variable edits
- Manual Python

Secrets and kill switches may remain pre-provisioned as infrastructure.
