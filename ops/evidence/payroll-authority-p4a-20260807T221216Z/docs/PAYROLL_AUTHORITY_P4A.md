# Payroll Authority P4A — Kuwait Statutory Architecture + Counsel-Gated Packaging

**Status:** implemented  
**Version:** 1.0.0  
**Date:** 20260808  
**Preserves:** P1–P3 · preview_non_authoritative · SYNTHETIC_ONLY · payment_processing=disabled · no native official PDF  
**Out of scope:** Inventing Kuwait rates · legal_claim approval · Mode A seal (P5) · payments · P4B counsel-signed rates · Employee App P1 · Setup Console · Auth Wave 2 Phase 6

---

## Goal

Complete **Kuwait statutory payroll architecture** so verified rates can plug in later (P4B) without redesigning the engine.

`legal_claim` remains **false**. Architecture fixtures are explicitly non-legal.

---

## Statutory schema (exact)

| Table | Role |
|---|---|
| `payroll_statutory_packages` | Country-scoped (`KW`) versioned packages; status draft / awaiting_legal_validation / approved / superseded |
| `payroll_statutory_rule_versions` | Rule families + output class + effective dates + fingerprints |
| `payroll_pifss_contribution_specs` | EE deduction / ER contribution / remittance obligation (distinct) |
| `payroll_eos_settlement_snapshots` | Separate EOS settlement (not monthly G2N); never auto-payable |
| `payroll_statutory_eval_runs` / `_lines` | Classified A/B/C/D evaluation artefacts |
| `payroll_statutory_events` | Audit |

**Rule families:** `pifss`, `ot_ordinary`, `rest_day_work`, `public_holiday_work`, `sick_leave_fractions`, `eos_indemnity`  
**Output classes:** `A_employee_net`, `B_employer_liability`, `C_settlement`, `D_remittance_reporting`

**Legal consumption rule:** `approval_status=approved` **AND** `legal_claim=true` **AND** `counsel_signed=true` **AND** `is_architecture_fixture=false`  
P4A **refuses** granting `legal_claim=true` (reserved for P4B).

---

## Calculation / liability / remittance boundary

| Class | Affects employee net? | Notes |
|---|---|---|
| **A** | Yes | OT/rest/PH/sick pay impact; PIFSS EE deduction |
| **B** | No | PIFSS employer contribution liability |
| **C** | No (settlement) | EOS indemnity snapshot — not a monthly payslip line |
| **D** | No | Remittance/reporting obligation — **not** payment processing |

P3 time-pay engines remain fail-closed for legal money until counsel-signed tables exist. Architecture fixtures may sync to P3 with `counsel_signed=false` and never satisfy `get_approved_rate()`.

---

## Module / API / UX

- `payroll_statutory_architecture_p4a.py`
- `ops/sql/payroll_statutory_architecture_p4a_v1.sql`
- `GET/POST /dashboard/posthire/payroll/authority-statutory/*` (distinct from Wave5 `/payroll/statutory`)
- UI: `PayrollStatutoryArchitecturePanel`

---

## Qualification

`ops/smoke-test-payroll-authority-p4a.py` → `ops/evidence/payroll-authority-p4a-*`

---

## Exact legal/rate inputs still required for P4B

1. **PIFSS** — Kuwaiti/GCC/expat eligibility; EE% + ER%; wage base/caps; remittance field map  
2. **Ordinary OT** — verified multiplier / hour rules + effective dates  
3. **Rest-day work** — distinct verified rule (not collapsed into ordinary OT)  
4. **Public-holiday work** — distinct verified rule  
5. **Sick-leave fractions** — verified day-band fractions + counsel citation  
6. **EOS indemnity** — verified basis, termination-reason variants, service banding/ceilings  

Each requires: `approved` + `legal_claim=true` + `counsel_signed=true` + provenance/citation. **Do not start P5 automatically.**
