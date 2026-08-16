# Production Readiness R4 — Truth-in-UI Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS`
**Phase:** R4 — Truth-in-UI
**Date:** 2026-08-12
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md` (owner accepted)
**Full pass:** `ops/PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r4-truth-ui-20260812T181712Z/`

---

## What freezes with R4

These are now binding contracts. Changing any of them requires a written amendment, not a silent UI default.

1. **A failed read is not an empty success.** Interviews, Overview work queue, and the named PostHire dependency reads must distinguish loading, genuine empty, error/retry, unavailable, and forbidden. API failure must not render “No interviews”, “No work”, or “No pending items”.
2. **Named surfaces use the shared data-state contract.** New customer-critical list/read UI on those paths uses `ResourceState` / `resolveListDataState` (or an equivalent that cannot collapse error into empty). Ad-hoc `data \|\| []` after a failed fetch is not an acceptable pattern on those surfaces.
3. **Overview composition flags are real.** `showWorkQueue` and `showRolePriority` control mounting. Disabled/unavailable sections must not mount empty shells. Sparse companies must look intentional.
4. **A control shown to a real user must perform a supported action.** Permanently disabled “Not implemented” production actions are hidden, not shown. Null delivery-center stubs stay gone.
5. **Authorization UX uses canonical permissions/roles.** Nonexistent role strings (`hr`, `admin`) are not used as client fallbacks. Frontend remains UX gating only; backend stays authoritative.
6. **Alerts & Delivery is page-gated, not only action-gated.** No nav entry and fail-closed direct navigation without a manage permission from the shared allowlist.
7. **Disabled source module → no new actionable employee notification.** Suppression is centralized in `deliver_employee_notification`. Historical rows are preserved. Re-enable restores new sends. Do not add a second notification engine.
8. **`migration-sync` is not a page.** The durable destination is Employees Migration Sync (`?page=employees&view=migration`). Legacy `?page=migration-sync` remaps there. Do not add a fake page to satisfy a link.
9. **Production surfaces never fall back to fake or silently-empty-on-error data** (charter). R4 is the UI half of that rule for the named current production paths.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen.
2. R3 (`PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`) remains frozen.
3. Waves 1–6 remain frozen as **domain authority**. Waves 4–6 remain not product-surface complete.
4. All Wave 4/6 capability remains global-OFF and company-gated.
5. `PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no rollout.
6. **R5 Wave 4/6 Surface Programme does not start from this amendment.** Owner review is required first.

## Deployment prerequisites

* Staging orchestrator must run the R4 `deliver_employee_notification` module gate.
* HR Web dashboard JS with `ResourceState` + composition flags + Alerts nav gate must ship together with that backend for the UI contracts to hold in a browser.
* Do not restore `PostHireDeliveryCenter` null stubs, `?page=migration-sync` as a real page, or `'hr'`/`'admin'` authorization fallbacks.

## Owner review

R4 is complete and frozen. Stop.

Do not begin R5 automatically.
