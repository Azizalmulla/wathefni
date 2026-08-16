# Employee App ↔ HR Dashboard Sync Hardening — PASS

| Field | Value |
|---|---|
| Stamp | `20260807T194248Z` (deploy) / live proofs `20260807T194623Z` |
| Verdict | **PASS** |
| Dashboard asset | `PostHire-MwO0aeVW.js` |
| Mobile OTA | `3d01d413-214f-4fa6-8ec5-3c10e48e8a1e` (canary) |
| Design | `ops/EMPLOYEE_HR_SYNC_HARDENING.md` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-hr-sync-hardening-20260807T194248Z/` |
| Frozen | Migration Sync P6.1 untouched · Auth Wave 2 Phase 6 not started |

## Module matrix

| Module | HR→App | App→HR | Live/stale | Verdict |
|---|---|---|---|---|
| Profile / `/app/me` | PASS | N/A | PASS | **PASS** — PTR + foreground + unlock refreshMe; HR PATCH reflected on re-fetch |
| Unlock overlay | PASS | N/A | PASS | **PASS** — post-dismiss soft refresh |
| Home / high-churn | PASS | PASS | PASS | **PASS** — `staleTime: 0` aligned with detail screens |
| Onboarding | PASS | PASS | PASS | **PASS** — HR 60s soft poll + mobile churn |
| Documents | PASS | PASS | PASS | **PASS** — renew invalidates onboarding |
| Leave | PASS | PASS | PASS | **PASS** — soft poll + staleTime 0 |
| Bank ESS | PASS | PASS | PASS | **PASS** — Bank panel visibility refetch |
| Org ESS | PASS | PASS | PASS | **PASS** — Reject + payroll gate parity |
| Shifts | PASS | N/A | PASS | **PASS** — staleTime 0 + foreground |
| App access card | PASS | PASS | PASS | **PASS** — 60s soft poll on open profile |
| Inbox | PASS | PASS | PASS | **PASS** — EN/AR catalog titles (`label_ar`) |
| Payslips / compliance_actions | N/A | N/A | N/A | **N/A** — still unimplemented stubs |
| Migration Sync | N/A | N/A | PASS | **PASS** — frozen, not modified |

## Proven

- Contract vitest: 5/5 PASS
- Static + live API smoke: PASS (`ops/smoke-test-employee-hr-sync-hardening.py`)
- HR title edit → immediate `/app/me` reflection (restored)
- Inbox titles: `App activation code` ↔ `رمز تفعيل التطبيق`
- Dashboard needles: `inboundQueue`, `employees.ess.approve.payroll`, Reject/Return

## Remaining true gaps (not blockers)

1. Device UI walk of PIN/Face ID unlock + PTR on physical canary after OTA lands (wiring + OTA shipped; owner/canary visual optional).
2. Variable-substituted notification **bodies** remain send-time language (titles localized).
3. Payslips / compliance_actions still intentionally unimplemented.
4. No cross-client push invalidation bus — 60s soft poll + foreground/unlock/PTR by design.

## What changed (no redesign)

Mobile: `employeeSoftRefresh`, foreground+unlock `refreshMe`, Profile PTR, high-churn staleTime, documents renew→onboarding, notifications `?locale=`.

HR: `FRESHNESS_MS.inboundQueue` soft polls (Leave, Onboarding, Compliance, Org ESS, App access); Bank RQ interval; Org ESS Reject + payroll permission split; dead `canDecide={false}` removed.

Backend: `catalog_label` + `label_ar`; `/app/notifications?locale=`.
