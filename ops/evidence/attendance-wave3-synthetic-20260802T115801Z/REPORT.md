# Attendance Wave 3 — Production Synthetic Ops Canary

**Stamp:** 20260802T115801Z
**Tenant scope:** WATHEFNI only
**Mode:** synthetic ops canary (no real clocking, no devices, no UI redesign)

## 1. Exact production flags and tenant scope
```
WATHEFNI_ATTENDANCE_OPS=on
WATHEFNI_ATTENDANCE_OPS_COMPANIES=WATHEFNI
WATHEFNI_ATTENDANCE_OPS_STORE=postgres
WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY=on
WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS=absence,early_leave
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
WATHEFNI_ATTENDANCE_IMPORT=off
WATHEFNI_ATTENDANCE_AUTHORITY=on
WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES=WATHEFNI
WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS=ATTW1C,ATTW2C,ATTW2E,ATTW2G,ATTW3,W1C-SYNTH|,W2C-SYNTH|,W2E-SYNTH|,W2G-SYNTH|,W3-SYNTH|
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965524
WATHEFNI_ATTENDANCE_CAPTURE_OPS=on
WATHEFNI_ATTENDANCE_CAPTURE_STORE=postgres
```
Synthetic markers only: `W3-SYNTH|` / `ATTW3` / `965524*`. Four real employees denied. External tenants denied.

## 2. Test results and evidence path
- Local ops smoke: 55/55 (failed=0)
- Production canary: 84/84 (failed=0)
- Evidence: `/Users/azizalmulla/Desktop/claw/ops/evidence/attendance-wave3-synthetic-20260802T115801Z`
- Remote: `/opt/wathefni/production-evidence/attendance-wave3-synthetic/20260802T115801Z`
- Backup: `/opt/wathefni/backups/production-pre-attendance-wave3-20260802T115801Z`

## 3. Workflows exercised
- Every exception kind open (missing in/out, ambiguous, incomplete, absence, lateness, early leave, connector)
- Assignment (owner / priority / due)
- Missing in/out lifecycle
- Late + early-leave correction
- Absence correction
- Approve / reject / apply separation
- Dual approval (distinct approvers; same-approver denied)
- Apply idempotency + concurrent apply (single winner fail-closed; same-key both ok)
- Employee dispute + reopen
- Stale row_version fail-closed
- Manager scope / unconfigured / self-denial
- Payroll lock denial
- Leave reversal preserves correction
- Approved attendance ↔ payroll snapshot reconcile
- Comments, attachments, append-only audit (update blocked)
- Isolation from real attendance_records, payroll_timesheets, employees, leave balances, reports
- No devices registered

## 4. Database and audit verification
```json
{
  "db": "wathefni",
  "attendance_rows": 42,
  "demo_seed": 42,
  "four_reals": 4,
  "leftover_w3_exceptions": 0,
  "audit_immutable_trigger": [
    "trg_att_ops_audit_immutable"
  ],
  "w3_devices": 0,
  "audit_events_total": 179,
  "capture_ingest_env": "off",
  "ops_synthetic_only": "on",
  "ops_companies": "WATHEFNI"
}
```
- Audit immutable trigger present
- Synthetic operational leftovers cleaned; append-only audit rows may remain by design

## 5. Failures, deviations, residual risks
- none for synthetic ops canary
- Staging onboarding freeze drift remains a **separate** pre-existing staging-tree issue — see `docs/STAGING_ONBOARDING_FREEZE_DRIFT.md`; **not** accepted as baseline.
- Residual: ops HTTP routes live for WATHEFNI but synthetic-only gated; real ingest/devices remain NO-GO and need separate qualification.
- Residual: append-only canary audit events retained until retention policy.

## 6. Final GO/NO-GO — synthetic ops only
**GO**

Still **NO-GO** (unchanged):
- Real punch ingest / biometric devices / connectors
- Real employee clocking
- Payroll money impact on real employees
- External tenants
- Attendance UI redesign
