# Payroll Authority Program — Architecture Plan (Audit Only)

**Status:** Phase 0 approved · **P1–P5 implemented** · **P6 production readiness + company entitlement implemented** (`ops/PAYROLL_AUTHORITY_P6.md`) — not a global Mode A unlock  
**Date:** 20260808  
**Scope:** Long-term Mode A (Wathefni payroll authority) + Mode B (external payroll authority)  
**Out of scope this doc:** Employee App P1 · Setup Console redesign · Auth Wave 2 Phase 6 · unlocking Mode A finalize

---

## 1. Target product model

Wathefni must support **two first-class money-authority modes** for any company:

### Mode A — Wathefni Payroll authority

```
Compensation setup
  → attendance + leave + variable inputs
  → deterministic gross-to-net
  → HR/payroll review + SOD
  → immutable finalization (money seal)
  → official PDF payslips
  → explicit employee release
```

Wathefni **owns** calculation and the sealed payroll result. Payment rails remain a **separate later boundary**.

### Mode B — External Payroll authority

```
External ERP/payroll calculates & pays (or confirms pay)
  → Wathefni imports/syncs authoritative results
  → same canonical payroll snapshot + payslip model
  → official PDF + employee release
```

Wathefni **mirrors** authority; it must never pretend it calculated Mode B nets.

### Shared end-state (already partially built)

Both modes terminate in the **same** employee architecture:

| Surface | Status |
|---|---|
| Payslip document versioning (`active` / `replaced` / `revoked`) | Built (Wave 3) |
| Explicit employee release gate (`not_released` / `released`) | Built (P0) |
| Employee App list/detail | Built (P0) |
| Official PDF (immutable snapshot → private storage → authenticated download) | Built (P0.1) for **external** eligibility |

**Mode A unlock for official PDF:** only after native results are true money authority — never by flipping `preview_non_authoritative` alone.

---

## 2. Why native is currently preview + synthetic-only

| Gate | Exact reason |
|---|---|
| `preview_non_authoritative` | Wave 2B is a **preview engine**, not a sealed money run. Honesty: `authoritative=False`, `wathefni_money_authority=False`, `native_gross_to_net_full=False`. |
| Unsupported in 2B | `pifss`, `overtime_premiums`, `sick_leave_pay_fractions`, `eos`, `public_holiday_rest_day_pay` |
| Attendance not in calc | Period can pin attendance source; native preview **ignores** attendance; export assembly returns empty stubs |
| `SYNTHETIC_ONLY` | Production default refuse real employees until non-synthetic qualification |
| `payment_processing=disabled` | Hard SQL + code — correct: calc ≠ payment |
| Official PDF native refused | P0.1 eligibility is `external_import` + `money_authority=external` only |

These gates are **safety architecture**, not tech debt to delete for green tests.

---

## 3. Design principles for a flexible Kuwait module

1. **Canonical components, company policies** — not per-employer formula spaghetti.
2. **Versioned calculation policy** — every sealed run cites `policy_version` + fingerprints.
3. **Effective-dated everything that affects money** — compensation, policy tables, nationality class.
4. **Separate concerns:**
   - company policy (OT multipliers, grace minutes, rounding)
   - statutory Kuwait (PIFSS / EOS / Art. 66–69 structure)
   - remittance / filing workflows
   - bank / WPS / payment confirmation
5. **Counsel-gated statutory rates** — structure may be modeled; rates/formulas stay `counsel_required` until signed tables exist.
6. **SME → enterprise scale:** same engine; larger tenants get more components, SOD, multi-branch cost centres, dual reopen — not a different calc core.
7. **No silent rewrite** of sealed money; corrections = new versioned run / payslip replace with audit.

### Recommended configuration model

| Layer | What lives here | Example |
|---|---|---|
| **Canonical component catalog** | Stable codes + kinds Wathefni understands | `BASIC`, `ALLOWANCE.*`, `DEDUCTION.*`, `OT_*`, `UNPAID_LEAVE`, `PIFSS_EE`, `PIFSS_ER` |
| **Company component map** | Which catalog items a company uses + labels EN/AR | Company enables `TRANSPORT`, custom `PHONE_ALLOWANCE` |
| **Employee compensation contract** | Effective-dated amounts / eligibility | Wave 1 contracts (reuse/extend) |
| **Company payroll policy (versioned)** | Rules that change calc behavior | OT premiums, rounding, unpaid handling, attendance grace |
| **Statutory rule tables (versioned, counsel-signed)** | Kuwait/GCC category rates | PIFSS ceilings; EOS tiers — **not hardcoded in code** |
| **Period run** | Locked inputs + policy version + fingerprints + status | Extends Wave 2B/4 concepts |
| **Sealed result snapshot** | Immutable money authority artifact | Mode A: Wathefni; Mode B: external mirror |
| **Payslip document** | Employee-facing projection of sealed result | Wave 3 + release + PDF |

**Custom earnings/deductions:** allowed as company-mapped catalog items with `component_kind` + `amount_unit` (`monthly` / `one_time` / later `hourly`/`daily`) and optional **formula hooks** limited to a small safe DSL (or “fixed amount / percent of base / percent of gross”) — not arbitrary scripts in v1 authority.

---

## 4. Capability matrix

| Capability | Current state | Long-term target | Missing work | Risk / authority |
|---|---|---|---|---|
| **Base salary** | Wave 1 contracts + 2B monthly basic proration | Mode A sealed run consumes approved contracts | Authoritative consumer of contracts (not preview label) | Claiming authority without seal |
| **Recurring allowances** | Contract components in preview | Catalog + company map + sealed run | Policy catalog; company enablement UX | Ad-hoc codes without provenance |
| **One-off allowances** | One-time contract + preview adjustments | Same + period adjustments with audit reason | First-class adjustment workflow into sealed run | Silent period edits |
| **Recurring deductions** | Fixed monthly in preview | Same + statutory EE share where counsel allows | PIFSS EE in calc (gated); company custom deductions | Encoding wrong statutory rates |
| **One-off deductions** | Preview adjustments | Sealed adjustments / recovery lines | Correction model tied to sealed runs | Mixing preview adj with money |
| **Effective-dated compensation** | Built (approve/replace, overlap fail-closed) | Same under Mode A | Wire into sealed run inputs assembly | Mid-period change disputes |
| **Company-specific components** | Partial (codes on contracts) | Catalog + map + labels EN/AR | Component catalog service | Formula spaghetti |
| **Attendance** | Exists as module; **not in native calc** | Approved snapshots → hours/absence/pay impact | Input assembly + pay rules | Wrong money from provisional hours |
| **Lateness / absence rules** | Not in payroll calc | Company policy: grace, deduct, half-day | Policy + attendance→pay bridge | Arbitrary deductions without policy version |
| **Unpaid leave** | Caller-supplied chargeable days in 2B | Auto from leave handoff classifications | Auto-assembly from Leave module | Double-count leave + absence |
| **Sick leave** | Explicitly unsupported (fractions) | Art. 69 bands via counsel table | Counsel-signed fraction table + leave type map | Hardcoding Art. 69 wrong |
| **Overtime** | Unsupported (`overtime_premiums`) | Written-order OT + premiums from policy/statutory | OT capture + policy multipliers + counsel ordinary premium | Claiming Art. 66 compliance |
| **Rest-day / public holiday** | Unsupported | Calendar + OT type premiums | Company calendar + counsel rates | Ambiguous 150%/200% practice |
| **Shift-based pay impact** | Shifts exist; not payroll money | Optional premium / night differential via policy | Bridge shifts→attendance→pay | Over-engineering for SMEs |
| **PIFSS** | Wave 5 **worksheets** only | In-calc EE/ER lines **or** remittance workflow (split clearly) | Counsel rates; category; remittance channel later | Treating worksheets as remittance |
| **EOS / indemnity** | Wave 5 worksheets; never auto payable | Settlement calc worksheet → optional payable on exit | Counsel Art. 51/53 + Law 17/2018 | Auto-paying EOS |
| **Calc vs remittance split** | Documented in Wave 0B; partially honored | Calc seals net; remittance/filing separate | Explicit workflow objects for remittance | Mixing filing into G2N |
| **Deterministic / idempotent calc** | Built in 2B (fingerprints) | Same for sealed runs | Authoritative policy version + seal | Re-run changing sealed money |
| **Configurable policies** | Preview policy version stub | Full company policy versions | Policy schema + UI + migration | One-employer hardcode |
| **Period locking** | Built Wave 1 | Lock before sealed calc | Enforce assembly-from-locked-only | Calc from open drift |
| **Reruns / corrections** | Preview supersede; payslip replace; close dual reopen | Sealed correction runs + payslip replace | Correction run type; employee re-release | Silent rewrite |
| **Money authority clarity** | Labels exist; native = preview | Mode A seal sets Wathefni authority; Mode B keeps external | Seal object + mode field on snapshot | Ambiguous authority |
| **Review / SOD** | Contracts + close SOD | Same for sealed Mode A runs | Bind 2B→seal approval path | Same actor approve+finalize |
| **Finalization as money seal** | Wave 4 close exists but non-authoritative | Close/seal **creates** money authority (Mode A) | Authority bit on seal; native PDF unlock criteria | Close without authority |
| **Payslip release / PDF** | P0/P0.1 proven | Mode A feeds same path once authoritative | Eligibility expand when Mode A ready | Unlocking native PDF early |
| **Payment confirmation** | Not built; processing disabled | Optional post-seal payment events | Payment event model + `payment_date` | Inventing payment_date |
| **Bank / WPS / remittance** | Contract validation / worksheets only | Adapters after seal | Per-bank formats; AS’HAL evidence — later | Building rails before seal |
| **Mode B external mirror** | Wave 2A + external payslip + official PDF | First-class vendor connectors | Real SAP/Oracle/bureau adapters; fill attendance stubs | Vendor_claimed false forever |
| **SME ↔ enterprise flexibility** | Synthetic WATHEFNI canary | Same core; progressive SOD/components | Packaging by company size | Two divergent engines |

---

## 5. Kuwait / counsel boundary (do not hardcode)

| Topic | In calc engine? | Separate workflow? | Counsel required? |
|---|---|---|---|
| Wage includes contractual allowances (Art. 55–56) | Component model | — | Structure known; counsel on edge cases |
| OT written order + premiums (Art. 66) | Policy + OT lines | OT authorization record | **Yes** for rates/limits claims |
| Sick leave pay fractions (Art. 69) | Leave→pay map | — | **Yes** for fractions |
| Annual leave eligibility 6 vs 9 months | Leave module | — | **Yes** (conflict in sources) |
| EOS tiers (Art. 51/53) | Settlement worksheet → optional payable | Exit workflow | **Yes**; Law 17/2018 interaction |
| PIFSS rates / ceilings / GCC nationals | Optional in-net EE/ER **or** remittance worksheet | Remittance/filing | **Yes** for all rates |
| Personal income tax | **N/A** (no PAYE) | — | Confirmed out of scope |
| AS’HAL / PAM wage monitoring | Evidence + export | Bank/PAM | Practice M — do not claim filing |
| Domestic workers (Law 68/2015) | Out of scope v1 | — | Separate product |

---

## 6. Payments boundary (explicit)

```
[Authoritative sealed payroll result]
        ↓
[Official payslips + employee release]   ← can exist WITHOUT payment
        ↓ (optional later)
[Payment instruction / bank file / WPS]
        ↓
[Payment confirmation event → payment_date]
```

**Rules:**

- Correct Mode A does **not** require payment processing.
- `payment_date` appears on payslip **only** when a confirmed payment event exists (or Mode B supplies authoritative paid-on date).
- Never invent `payment_date`.
- Keep `payment_processing=disabled` until bank/WPS adapters are qualified.

---

## 7. Reuse vs extend vs rebuild

### Reuse as-is (shared end-state)

- Wave 3 payslip documents + history (replace/revoke)
- Employee release / unrelease / notify (P0)
- Official PDF generator + private storage + employee download (P0.1) — extend eligibility later
- Wave 1 periods, modes (`native` / `external` / `parallel_shadow`), SOD helpers
- Wave 1 compensation contracts (effective-dated) as Mode A input SoR
- Wave 4 close/reopen/SOD patterns as the **seal** spine
- Wave 5 worksheet pattern for counsel-gated statutory review
- Wave 2A external import path as Mode B foundation
- Fingerprinting / idempotency patterns from Wave 2B

### Extend (do not throw away)

| Asset | Extension |
|---|---|
| Wave 2B preview engine | Evolve into **authoritative calc engine** behind new policy version + seal — or keep preview parallel and add `payroll_calc_authority` module that shares math carefully |
| Wave 1 contracts | Company component catalog + richer kinds |
| Wave 4 close | Promote to **money seal** when Mode A criteria met; stamp `money_authority=wathefni` |
| Leave handoff | Auto-assemble unpaid/sick classifications into period inputs |
| Attendance snapshots | Auto-assemble into period inputs |
| Official PDF eligibility | Add Mode A sealed native when authority proven |

### Rebuild / new (do not fake inside preview)

- Company payroll **policy version** product (not only preview_policy stub)
- Canonical **component catalog** + company map
- **Input assembly** service (attendance + leave + OT + adjustments → locked period inputs)
- **Sealed run** as first-class money authority object (Mode A) distinct from preview runs
- OT / sick / PH rule engines fed by counsel tables
- Payment confirmation events (future)
- Real external vendor connectors (Mode B maturity)

### Stay counsel-gated until signed

- All statutory **rates** (PIFSS, OT premiums, sick fractions, EOS formulas, GCC schemes)
- Any product copy claiming “Kuwait labour law compliant”
- Automatic EOS payable
- Automatic PIFSS remittance completion

---

## 8. Phased implementation plan (recommended boundaries)

Phases are ordered by **authority dependency**, not forced marketing names.

### Phase 0 — Program freeze & contracts (docs only) ✅ this document

- Lock Mode A/B definitions, payment boundary, counsel gates
- Do not flip flags

### Phase 1 — Authority model & canonical snapshot ✅ P1

**Goal:** One sealed payroll result model both modes write into.

- `payroll_authority_snapshots` (+ lines/events) with `money_authority ∈ {wathefni, external}`
- Mode B: `seal_from_external_import` → sealed external; payslip/PDF consume sealed
- Mode A: `seal_from_native_preview` exists but **refuses** Wathefni authority until finalize phase
- Period close remains non-authority; payment rails disabled
- **Exit met:** Mode B seals/mirrors; Mode A seal path refuses; preview stays preview

See `ops/PAYROLL_AUTHORITY_P1.md` + `ops/smoke-test-payroll-authority-p1.py`.

### Phase 2 — Input assembly (attendance + leave) ✅ P2

**Goal:** Locked period has complete, auditable inputs without manual JSON.

- `payroll_input_snapshots` assemble approved attendance + approved leave + schedule/calendar facts
- Readiness: assembling / needs_review / ready / locked / superseded
- Overlap precedence: unpaid leave suppresses absence; unapproved leave excluded
- OT/rest-day/PH captured as **facts only** (no money)
- **Exit met:** Mode A can later consume locked input FP; P1 money authority unchanged

See `ops/PAYROLL_AUTHORITY_P2.md` + `ops/smoke-test-payroll-authority-p2.py`.

### Phase 3 — Earnings / deductions / OT / time-pay rules

**Status:** **implemented** — see `ops/PAYROLL_AUTHORITY_P3.md` + `ops/smoke-test-payroll-authority-p3.py`.

**Goal:** Company-configurable G2N coverage beyond fixed monthly.

- Component catalog + company map
- Period adjustments (one-off) with reasons
- OT capture + policy multipliers (counsel tables for statutory premiums)
- Lateness/absence policy hooks
- Sick leave fractions behind counsel tables (or remain worksheet-only if unsigned)
- **Exit:** Preview covers component/time-pay architecture with honesty still `preview` until seal phase; OT/rest/PH/sick money fail closed without counsel-approved rates

### Phase 4 — Kuwait statutory packaging

**Status:** **P4A implemented** (architecture + counsel-gated packaging) — see `ops/PAYROLL_AUTHORITY_P4A.md`.  
**P4B public baseline (partial):** OFFICIAL_CLEAR Wathefni-owned Kuwait statutory rules activated — see `ops/PAYROLL_AUTHORITY_P4B.md`. Ambiguous/special-regime cases remain gated. Mode A / PDF / payments still locked.

**Goal:** Clear calc vs remittance split.

- PIFSS: category-aware contributory wage → either in-net lines **or** remittance worksheet (product choice per company)
- EOS: exit settlement worksheet → never auto-payable without explicit Mode A settlement product
- Counsel-signed rate table versions
- **P4A exit:** Statutory architecture operable with A/B/C/D boundaries; fixtures never legally approved; legal money still fail-closed
- **P4B exit:** Verified Kuwait tables approved with counsel sign-off; still synthetic-only until Phase 6

### Phase 5 — Authoritative finalize + corrections

**Status:** **implemented** on synthetic canary — see `ops/PAYROLL_AUTHORITY_P5.md`.  
**Goal:** Mode A money seal (done for SYNTHETIC_ONLY).

- Promote sealed run to `money_authority=wathefni` only when:
  - inputs assembled from locked period
  - policy version frozen
  - SOD approvals complete
  - unsupported rules either resolved or explicitly excluded by company policy with audit
- Payslip generate from sealed run → `money_authority=wathefni` → official PDF eligibility
- Correction = new sealed run + payslip replace + re-release (reuse Wave 3)
- Dual-control reopen retained
- **Exit:** Mode A end-to-end on **synthetic** subjects with residual-zero; native official PDF allowed **only** for sealed Wathefni runs

### Phase 6 — Real-production qualification

**Status:** **implemented** as controlled company entitlement — see `ops/PAYROLL_AUTHORITY_P6.md`.  
**Goal:** Replace blanket `SYNTHETIC_ONLY` with company-level production entitlement; qualify Mode A OS end-to-end.

Delivered:

1. Entitlement states: `disabled` / `preview_only` / `authoritative_allowlisted` / `authoritative`
2. Payroll readiness validator + Setup Console schema contract
3. Independent expected-results oracle + archetype/scenario matrix
4. Exception-first review + advisory variance layer
5. Scale timings (10 / 100 / 1000)
6. WATHEFNI controlled allowlisted entitlement (not global unlock)
7. Mode B coexistence preserved; payment/WPS still out of scope

**Unrestricted customer rollout** remains gated by remaining gaps in `PAYROLL_AUTHORITY_P6.md`.

---

## 9. What must be true before removing the gates

| Gate | Remove only when |
|---|---|
| Treating Wave 2B preview as money | Never — preview stays preview; seal is separate |
| `preview_non_authoritative` on **sealed Mode A** results | Phase 5 exit criteria met |
| Native official PDF refusal | Sealed run has `money_authority=wathefni` |
| `SYNTHETIC_ONLY` for a company | Phase 6 real-employee canary + company opt-in |
| `payment_processing=disabled` | Separate payment-rail program — **not** required for Mode A calc authority |

---

## 10. Sequencing recommendation vs Mode B

**Recommended parallel track:**

1. **Mode B maturity** can proceed earlier commercially (real vendor connector + non-synthetic unlock for external mirror) using existing P0/P0.1 payslips — without claiming Wathefni calc.
2. **Mode A** follows Phases 1→6 above; employee experience stays identical.

Do **not** block Mode B customers on Mode A OT/PIFSS completion.

---

## 11. Explicit non-goals (until reviewed)

- Do not implement any phase in this document yet
- Do not start Employee App P1
- Do not start Setup Console redesign
- Do not start Auth Wave 2 Phase 6
- Do not flip `preview_non_authoritative` / `SYNTHETIC_ONLY` / `payment_processing` to pass tests

---

## 12. Primary code / doc anchors

- Waves: `payroll_authority_wave1.py`, `payroll_external_adapter_wave2a.py`, `payroll_native_preview_wave2b.py`, `payroll_payslip_wave3.py`, `payroll_payslip_official_pdf.py`, `payroll_close_export_wave4.py`, `payroll_pifss_eos_wave5.py`
- Freezes: `ops/PAYROLL_WAVE{1,2A,2B,3,4,5}_*_FREEZE.md`, `ops/PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md`
- Research: `ops/PAYROLL_WAVE0B_KUWAIT_GCC_ARCHITECTURE_RESEARCH.md`
- Employee payslips: `ops/EMPLOYEE_PAYSLIPS_P0.md`, `ops/EMPLOYEE_PAYSLIPS_P0_1.md`
