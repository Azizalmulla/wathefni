# Payroll Authority P3 — Kuwait-First Payroll Components + Time-Pay Rules

**Status:** implemented  
**Version:** 1.0.0  
**Date:** 20260808  
**Preserves:** P1 sealed money · P2 locked inputs · Payslips P0/P0.1 · SYNTHETIC_ONLY · payment_processing=disabled  
**Out of scope:** Mode A money seal · native official PDF · PIFSS/EOS rates (P4) · payments · payment_date · Employee App P1 · Setup Console · Auth Wave 2 Phase 6

---

## Goal

Locked P2 facts + effective-dated compensation + versioned company payroll policy → **deterministic Mode A preview** component lines (gross / deductions / net).

`money_authority` remains **`preview_non_authoritative`**.

---

## Component / policy schema (exact)

| Table | Role |
|---|---|
| `payroll_component_catalog` | Canonical codes (P1 + P3 seeds: PHONE, BONUS, COMMISSION, LOAN, LATENESS, ABSENCE, CUSTOM.*) |
| `payroll_company_policy_versions` | Versioned, effective-dated company policy (attendance mode, lateness/absence/OT/rest/PH/sick flags, rounding, fingerprint) |
| `payroll_rate_tables` | Counsel-gated rate families: `ot_ordinary`, `rest_day_work`, `public_holiday_work`, `sick_leave_fractions` |
| `payroll_company_components` | Company-configured / custom components bound to catalog |
| `payroll_component_assignments` | Employee or group effective-dated amounts |
| `payroll_one_off_adjustments` | Period-scoped approved one-offs |
| `payroll_calc_preview_runs` | Versioned preview run header + fingerprints |
| `payroll_calc_preview_employee_results` | Per-employee totals / blockers / warnings |
| `payroll_calc_preview_lines` | Component lines with provenance |
| `payroll_calc_preview_events` | Audit |

**Policy attendance modes:** `required | informational | ignored`  
**Calc money authority CHECK:** `preview_non_authoritative` only  
**No arbitrary executable formulas/scripts.**

---

## Calculation architecture

```
locked input_snapshot_id (P2)
  + approved policy_version_id
  + compensation contracts/components (Wave 1)
  + company components / assignments / one-offs
  + catalog fingerprint
  → payroll_calc_preview_runs (content_fingerprint)
  → employee results + component lines
```

1. Refuse unless input snapshot status = `locked`
2. Resolve approved policy (explicit id or effective-dated)
3. Prorate monthly contract components by active calendar days; mid-period hire/leaver/salary change; fail closed on overlapping approved contracts
4. Attendance money only when policy mode ∉ {informational, ignored}
5. Unpaid leave → `UNPAID_LEAVE`; absences skipped when unpaid/paid leave overlap / suppressed
6. Lateness only when `lateness_money_enabled`
7. OT / rest-day / PH / sick: if money enabled and no counsel-approved rate table → **blocker `counsel_rate_required`** (no silent rates)
8. Identical inputs → identical `content_fingerprint` (idempotent return of existing run)

---

## Module / API / UX

- `wathefni-orchestrator/payroll_components_policy_p3.py`
- `wathefni-orchestrator/ops/sql/payroll_components_policy_p3_v1.sql`
- `GET /dashboard/posthire/payroll/components`
- `POST .../components/policy`
- `POST .../components/company-components`
- `POST .../components/assignments`
- `POST .../components/adjustments`
- `POST .../components/calc`
- `GET .../components/calc/{calc_run_id}`
- UI: `PayrollComponentsPolicyPanel` on Payroll Run + Hours

---

## Qualification

`ops/smoke-test-payroll-authority-p3.py` → `ops/evidence/payroll-authority-p3-*`

---

## Blockers for P4

1. Counsel-signed Kuwait OT / rest-day / PH multipliers and sick-leave fraction tables
2. PIFSS contributory wage packaging (employee + employer) — structure reserved, rates not applied
3. EOS indemnity worksheet / settlement path — reserved, not calculated
4. Remittance vs in-net statutory product choice per company
5. Do **not** unlock Mode A seal or native official PDF in P4; that remains P5
