# Payroll Authority P2 — Attendance + Leave Input Assembly

**Status:** implemented  
**Version:** 1.0.0  
**Date:** 20260807  
**Preserves:** P1 sealed money authority · Payslips P0/P0.1 · SYNTHETIC_ONLY · payment_processing=disabled  
**Out of scope:** OT/sick/PH/PIFSS money · Mode A finalize · P3 component rules · payments · Employee App P1 · Setup Console · Auth Wave 2 Phase 6

---

## Goal

Canonical bridge: **Attendance + Leave → versioned immutable payroll input snapshot** for future Mode A.

Facts only — no Kuwait statutory money calculation in P2.

---

## Schema

| Table | Role |
|---|---|
| `payroll_input_snapshots` | Header: period, mode, fingerprints, readiness, lock |
| `payroll_input_snapshot_employees` | Per-employee span + summaries |
| `payroll_input_snapshot_lines` | Fact lines with provenance |
| `payroll_input_snapshot_issues` | Blockers / warnings / info |
| `payroll_input_snapshot_events` | Audit |

**Status:** `assembling | needs_review | ready | locked | superseded`  
**attendance_payroll_mode:** `required | informational | ignored`  
**P1 bridge:** nullable `payroll_authority_snapshots.input_snapshot_id`

---

## Overlap / precedence rules

1. Only **approved** leave affects payroll inputs  
2. Pending / rejected / cancelled / withdrawn → excluded (info issue)  
3. Approved **unpaid** leave **suppresses** attendance absence for the same date (no double count)  
4. **Paid** leave must not become unpaid absence  
5. OT / rest-day work / public-holiday work → distinct fact line kinds with `money_impact=null`  
6. Overnight shifts: `ends_next_day` / `overnight_shift` facts; timezone default `Asia/Kuwait`  
7. Mid-period hire/leaver from employment dates; leave clipped to active ∩ period  

---

## Readiness / locking

| Transition | Behavior |
|---|---|
| Assemble | Build snapshot → `needs_review` if blockers (required mode) else `ready` |
| Lock | Allowed when `ready`; `needs_review` fail-closed |
| Locked + source change | Refuse silent rewrite |
| Correction path | `supersede_input_snapshot` → prior `superseded` + new version |
| Informational mode | Attendance gaps are warnings; do not block lock |
| Ignored mode | Attendance not required for payroll readiness |

---

## Module / API / UX

- `payroll_input_snapshot_p2.py` + `ops/sql/payroll_input_snapshot_p2_v1.sql`
- `POST /dashboard/posthire/payroll/inputs/assemble`
- `POST /dashboard/posthire/payroll/inputs/{id}/lock`
- `GET /dashboard/posthire/payroll/inputs/readiness`
- `GET /dashboard/posthire/payroll/inputs/{id}`
- UI: `PayrollInputReadinessPanel` on Payroll Run + Hours surfaces

---

## Qualification

`ops/smoke-test-payroll-authority-p2.py` → `ops/evidence/payroll-authority-p2-*`

---

## Blockers for P3

1. Component / time-pay rules engine  
2. Counsel-gated OT / sick / PH money  
3. Mode A authoritative finalize still locked  
4. SYNTHETIC_ONLY  
5. payment_processing disabled  
