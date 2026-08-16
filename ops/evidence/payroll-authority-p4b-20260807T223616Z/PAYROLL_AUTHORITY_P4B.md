# Payroll Authority P4B — Kuwait Public Statutory Baseline Activation

**Status:** implemented (partial activation — OFFICIAL_CLEAR only)  
**Version:** 1.0.0  
**Policy version:** `KW_PUBLIC_BASELINE_v1.0.0`  
**Date:** 20260808  
**Depends on:** P4A architecture frozen  
**Preserves:** preview_non_authoritative · SYNTHETIC_ONLY · Mode A locked · no native official PDF · payment_processing=disabled

---

## Model (3 layers)

1. **Kuwait statutory baseline (Wathefni-owned)** — OFFICIAL_CLEAR public rules with source provenance and policy version  
2. **Company payroll policy** — operating choices; never redefines mandatory Kuwait statutory formulas  
3. **Exception / special regime** — review-gated (GCC, oil, wage-base mapping, Law 17/2018, etc.)

---

## Activated OFFICIAL_CLEAR (this release)

| Family | Rule | Source | Effective |
|---|---|---|---|
| `ot_ordinary` | +25% / mult 1.25 + Art.66 caps metadata | Law 6/2010 Art.66 | 2010-02-21 |
| `rest_day_work` | ≥50% + compensatory day / mult 1.5 | Law 6/2010 Art.67 | 2010-02-21 |
| `public_holiday_work` | double + day off / mult 2.0 | Law 6/2010 Art.68 | 2010-02-21 |
| `sick_leave_fractions` | 15@100 / 10@75 / 10@50 / 10@25 / 30@0 | Law 6/2010 Art.69 | 2010-02-21 |
| `eos_indemnity` | Arts 51–53 structure (C settlement) | Law 6/2010 Arts 51–53 | 2010-02-21 |
| `pifss` | Basic/Supp/Pension-increase/Unemployment EE·ER % + caps; remittance timing (D) | PIFSS official FAQ | rates from FAQ; unemployment from 2013-05-01 |

`counsel_rate_required` is removed **only** for these exact activated rule versions/families when the public baseline resolves.

---

## Still gated (fail-closed)

- PIFSS wage-base mapping (company/statutory classification required — salary ≠ auto PIFSS base)  
- PIFSS financial remuneration 2.5% (18-year trigger)  
- GCC extension home rates  
- Expatriate residual schemes confirmation  
- OT night +50% (UNSUPPORTED)  
- Hourly divisor / 26-day convention  
- PH calendar extras beyond Art.68 list  
- Sick year basis + pay base  
- EOS remuneration base classification  
- EOS × PIFSS Law 17/2018 (Kuwaiti path)  
- Fixed-term resignation edge; oil special regime  

---

## Module / SQL / API

- `wathefni-orchestrator/payroll_statutory_baseline_p4b.py`  
- `wathefni-orchestrator/ops/sql/payroll_statutory_baseline_p4b_v1.sql`  
- Classification: `ops/payroll_authority_p4b_public_baseline_classification_v1.json`  
- APIs under `/dashboard/posthire/payroll/authority-statutory-baseline/*`  
- Smoke: `ops/smoke-test-payroll-authority-p4b.py`

---

## Setup Console ownership matrix

See `setup_console_ownership_matrix()` in the module and § below in evidence. Wathefni owns Kuwait law tables; companies provide classifications, components, OT eligibility, cut-offs, calendars, and special-regime flags — never “what is Kuwait OT %?”.

---

## Qualification

`ops/smoke-test-payroll-authority-p4b.py` → `ops/evidence/payroll-authority-p4b-*`  
Also re-run P1–P4A smokes after activation.

**Do not start P5 automatically.**
