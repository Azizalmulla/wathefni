# Payroll Authority P5 — Mode A Authoritative Finalize

**Status:** implemented (SYNTHETIC_ONLY)  
**Version:** 1.0.0  
**Date:** 20260808  
**Depends on:** P1–P4B frozen · `KW_PUBLIC_BASELINE_v1.0.0`  
**Preserves:** preview_non_authoritative on calc rows · Mode B external · payment_processing=disabled · no invented payment_date · SYNTHETIC_ONLY

---

## Mode A authority transition (exact)

| Stage | Artifact | `money_authority` |
|---|---|---|
| P3 calculate | `payroll_calc_preview_runs` | **`preview_non_authoritative` forever** |
| P5 draft→approved | `payroll_mode_a_finalize_runs` | `pending_seal` |
| P5 finalize seal | **new** `payroll_authority_snapshots` | **`wathefni`** |
| Payslip | `payroll_payslip_documents` `source_kind=native_authoritative` | **`wathefni`** |
| Official PDF | eligible only when linked to current sealed wathefni snapshot | — |

**Never** flip a preview/calc row in place to grant authority.  
**Never** treat Wave 4 period close as money seal.

---

## Finalize / SOD model

Progression (reuse clear names, not duplicates):

`draft` → `in_review` → `approved` → `finalized`

Company policy (`payroll_mode_a_company_finalize_policy`) — SME defaults:

| Setting | Default |
|---|---|
| `require_review_step` | true |
| `require_distinct_approver` | true (creator ≠ approver) |
| `require_distinct_finalizer` | true (creator ≠ finalizer) |
| `allow_approver_as_finalizer` | true (SME-friendly) |

Enterprise can set `allow_approver_as_finalizer=false` and keep approve/export SOD via Wave 1 helpers.

Repeat finalize on same calc is **idempotent**.

---

## Correction model

Sealed `money_authority=wathefni` is immutable.

| Event | Handling |
|---|---|
| Bad input before release | New locked P2 + new P3 calc + new finalize → `replace_mode_a_authority` |
| After payslip release | Replace authority → new payslip version → re-release; prior payslip/history retained |
| Attendance/leave/comp/statutory correction | Same: new versions, never erase history |

Prior snapshot: `status=replaced`, `superseded_by=<new>`; new has `replaces_snapshot_id`.

---

## Fail-closed statutory

P4B OFFICIAL_CLEAR families participate when policy enables money.

Gated classifications block seal **only when applicable** (employee flags / GCC / oil / Kuwaiti EOS×PIFSS / missing PIFSS wage map). Unaffected employees are not blocked.

---

## Module / SQL / smoke

- `wathefni-orchestrator/payroll_authority_mode_a_p5.py`
- `wathefni-orchestrator/ops/sql/payroll_authority_mode_a_p5_v1.sql`
- Extends: P1 `insert_wathefni_sealed_snapshot`, Wave 3 wathefni payslip, official PDF Mode A eligibility
- Smoke: `ops/smoke-test-payroll-authority-p5.py`

---

## P6 blockers (do not auto-start)

- SYNTHETIC_ONLY still on  
- Real employees blocked  
- Payment processing / WPS / bank rails out of scope  
- No invented `payment_date`  
- Need: real allowlist canary, residual-zero sample, company opt-in, release/PDF re-prove, rollback drill  

**Do not start:** Employee App P1 · Setup Console · Auth Wave 2 Phase 6
