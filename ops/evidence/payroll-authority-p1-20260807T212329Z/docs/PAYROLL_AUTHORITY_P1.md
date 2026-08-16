# Payroll Authority P1 — Kuwait-First Canonical Money Authority + Sealed Snapshot

**Status:** implemented  
**Version:** 1.0.0  
**Date:** 20260807  
**Scope:** Mode B seal + Mode A foundation only  
**Out of scope:** P2 input assembly · OT/statutory calc · Mode A finalize · payments · Employee App P1 · Setup Console · Auth Wave 2 Phase 6

---

## Verdict gate

Qualification: `ops/smoke-test-payroll-authority-p1.py` → evidence under `ops/evidence/payroll-authority-p1-*`.

---

## Authority modes

| Mode | `money_authority` | P1 behavior |
|---|---|---|
| **A — Wathefni** | `wathefni` | Schema + `seal_from_native_preview` **REFUSED** (`mode_a_wathefni_seal_not_unlocked`) |
| **B — External** | `external` | `seal_from_external_import` creates sealed snapshot |

**Frozen:** Wave 2B / native payslips remain `preview_non_authoritative`. Preview never becomes official by flipping a flag.

**Period close ≠ money seal.** Wave 4 `close_run` remains finance/SOD spine and does not grant money authority.

---

## Sealed snapshot schema

### Tables

| Table | Role |
|---|---|
| `payroll_authority_snapshots` | Immutable sealed money header |
| `payroll_authority_snapshot_lines` | Canonical component lines |
| `payroll_authority_snapshot_events` | Audit |
| `payroll_component_catalog` | Kuwait-ready identity hooks (no formulas) |

### Header fields (minimum)

`authority_snapshot_id`, `company_code`, `employee_key`, `period_id?`, `period_start`, `period_end`, `currency=KWD`,  
`money_authority ∈ {wathefni, external}`, `source_kind`, `source_mode`, `status ∈ {sealed, replaced, revoked}`,  
`import_run_id` / `preview_run_id` / `external_run_id`, `source_fingerprint`, `content_fingerprint`,  
`calculation_policy_version?`, `compensation_source` / `compensation_version`,  
`totals_earnings|deductions|gross|net`, `snapshot_payload`, `provenance`,  
`sealed_at`, `sealed_by_phone`, `approval_actor_chain`, `replaces_snapshot_id`, `superseded_by`, `payslip_id?`,  
`payment_processing=disabled`, `posts_payment=false`

### Uniqueness

- One **current** sealed per `(company_code, employee_key, period_start, period_end)`
- One sealed per `(company_code, import_run_id, employee_key)` when import-linked

### Component identity (P1-compatible with future P3)

Catalog codes include `BASIC`, allowances, deductions, `UNPAID_LEAVE`, `SICK_LEAVE`, `OT_*`, `PIFSS_*`, `EOS_INDEMNITY`, `EXTERNAL.OPAQUE` with EN/AR labels, category, counsel_gated flags. **No statutory rates/formulas.**

---

## Authority transitions

```
Mode B:
  import_external_results
    → seal_from_external_import   # money_authority=external, status=sealed
    → generate_external_payslip_from_sealed / seal_and_generate_external_payslip
    → release (P0) → official PDF (requires authority_snapshot_id)

Mode A (P1 foundation only):
  calculate_native_preview
    → seal_from_native_preview → REFUSED
  native official PDF → still refused

Correction:
  sealed → replace_authority_snapshot → prior=replaced + new sealed
  (never silent monetary UPDATE)

Stale:
  second different import for same employee/period → stale_source_cannot_overwrite_sealed
  (must replace)
```

---

## Official PDF eligibility (P1)

```
source_kind=external_import
AND money_authority=external
AND authority_snapshot_id → sealed snapshot with money_authority=external
```

Native preview never eligible. Period close alone never eligible.

---

## Module / SQL

- `wathefni-orchestrator/payroll_authority_snapshot_p1.py`
- `wathefni-orchestrator/ops/sql/payroll_authority_snapshot_p1_v1.sql`
- Official PDF eligibility tightened in `payroll_payslip_official_pdf.py` (v1.1.0)
- Wave 3 auto-links sealed snapshot on external generate/replace (v1.3.0)

---

## Remaining blockers for P2

1. Attendance + leave input assembly into sealed Mode A path  
2. Mode A authoritative-finalize still locked  
3. `SYNTHETIC_ONLY` remains  
4. Counsel-gated statutory rates  
5. `payment_processing=disabled`; no invented `payment_date`
