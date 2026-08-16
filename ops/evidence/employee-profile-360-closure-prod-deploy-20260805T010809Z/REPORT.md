# Employee Profile / 360 — Final Refinement & Closure

**Status:** LIVE · stamp `20260805T010809Z`  
**Evidence:** `ops/evidence/employee-profile-360-closure-prod-deploy-20260805T010809Z/`  
**Bundle:** `PostHire-BBh-0pcx.js`  
**Freeze posture:** Employees 360 controlled-rollout freeze remains; this wave is bugfix / HR-language / deep-link correctness only (no new E360 feature surface, no backend contract change, no payroll calculation change).

## Scope delivered

Low-risk UX and correctness on the Employee Profile / directory overlays:

- Body scroll lock + focus restore on Add / Edit / Import / Activation / Approver overlays
- Edit modal RTL + phone label parity with Add (no “Phone / WhatsApp” combo)
- Status approver picker dialog (no `window.prompt`); activation reason via `confirm.withReason`
- Softened internal-test approval copy; activation handoff without invite-id platform language
- Profile `dir` RTL, documents section anchor, Open in Attendance / Shifts / Payroll
- Documents description no longer duplicates onboarding outstanding counts
- Assignment history soft-keep + HR language (no Wave 4 jargon)
- Calendar / history deep-link sync via `popstate` (+ nudge from Calendar projection open)

## Out of scope (intentional)

- Payroll/shifts as Calendar projections (already deferred)
- Backend profile contract / manager name enrichment API
- Removing existing timesheet approve/reject on profile (existing `payroll.manage` gate preserved)
- Broad Employees / Workforce redesign

## Rollback

```bash
/opt/wathefni/backups/production-pre-employee-profile-360-closure-20260805T010809Z/ROLLBACK.sh
```

## Tests

- Vitest: `EmployeeProfileClosureContract` + directory contract + profile repro — PASS  
- `smoke-test-employees360-freeze-regression.py` — 57/57 PASS  
- Prod bundle markers — `PROFILE_CLOSURE_SMOKE_OK`; Calendar UX preserved

## GO / NO-GO

| Decision | Result |
|---|---|
| Profile closure deploy | **GO** |
| Full web E2E / production qualification wave | **GO** to begin (profile is calm enough; remaining qualification is end-to-end across modules, not blocked on this surface) |
| Reopen Employees 360 redesign | **NO-GO** without new owner change-control |
