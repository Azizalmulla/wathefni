# Employee App ↔ HR Dashboard Sync Hardening

Audit-driven freshness hardening. **No module redesign. No Auth Wave 2 Phase 6. Migration Sync P6.1 untouched.**

## Goals

1. Employee Profile (`/app/me`) refreshes on foreground + pull-to-refresh + post-unlock.
2. Unlock overlay no longer creates a silent stale window.
3. High-churn workflows (onboarding, documents, leave, bank, shifts) use `staleTime: 0` and shared soft refresh.
4. HR inbound queues soft-poll every 60s while visible (Leave, Onboarding, Compliance, Org ESS, Bank review, App access card).
5. Org ESS Reject + payroll-step permission parity with Bank.
6. Documents renew invalidates onboarding.
7. Inbox titles localize EN/AR via catalog `label_ar`.

## Authority

- `/app/me` remains the Employee App authority for profile fields + feature flags (same `employee_app_public` as `/app/profile.employee`).
- `/app/profile` stays available for onboarding completion enrichment; Profile tab does **not** dual-source.

## Soft refresh pattern

Mobile: `softRefreshEmployeeSurfaces(queryClient, refreshMe)` — called from `ForegroundQueryRefresh` and `LocalUnlockShell.dismissUnlock`.

HR: reuse `useVisibilitySoftPoll` / `useVisibilityRefetchInterval` with `FRESHNESS_MS.inboundQueue` (60s). No new realtime bus.

## Qualification

```bash
cd apps/wathefni-dashboard && npx vitest run src/posthire/EmployeeHrSyncHardeningContract.test.ts
python3 ops/smoke-test-employee-hr-sync-hardening.py
# optional live:
# WATHEFNI_EMPLOYEE_TOKEN=… WATHEFNI_DASHBOARD_TOKEN=… python3 ops/smoke-test-employee-hr-sync-hardening.py
```

Evidence: `ops/evidence/employee-hr-sync-hardening-*`
