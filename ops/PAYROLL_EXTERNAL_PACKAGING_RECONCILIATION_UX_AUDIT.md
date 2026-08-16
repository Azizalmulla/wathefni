# External Payroll Packaging & Reconciliation — UX / Packaging Audit

**Mode:** research + product architecture only  
**Date:** 2026-08-03  
**Prerequisite freezes:** `PROD_SYNTHETIC_PAYROLL_FINAL_GO` · Wave 2A · Wave 2A-C · Waves 3–5  
**This document does not code, deploy, reopen money rails, or start a vendor connector.**

---

## Executive verdict

| Question | Verdict |
|---|---|
| Can a real HR/finance team run the frozen external flow **without engineering** today? | **NO** |
| Is the architecture direction right (external = money authority)? | **YES — keep** |
| Should Wathefni rebuild as a Kuwait payroll bureau (Menaitech/ZenHR competitor)? | **NO** |
| Is there a proven gap that justifies a **narrow** next wave? | **YES — operability only** |
| Real money / vendor connector / WPS / bank / PIFSS remittance / AI / native G2N authority? | **NO-GO** |

**Bottom line:** Waves 1–5 proved the **control-tower contract** (export → import → quarantine → reconcile → payslip docs → close drafts). Packaging for a buyer operator is unfinished: setup is invisible, handoffs require UUIDs, quarantine cannot be worked, export rollback is broken in the UI path, and “input export” does not yet package live attendance/leave/shifts. Fix **operability and packaging clarity** — do not reopen money.

---

## 1. Current product truth (frozen end-to-end)

Honesty copy already states the product correctly:

> External system is money authority. Payment processing is disabled. Imports are mirror-only and never become Wathefni payment authority.

| Step | What exists today | Operator-visible? |
|---|---|---|
| **Mode selection** | `native \| external \| parallel_shadow` in Wave 1 settings; default `native`; always `payment_processing=disabled` | **No** dashboard setup UI — blocked readiness only |
| **Compensation / input readiness** | Approved effective-dated contracts required; wrong mode / payment flag / missing period / zero contracts → Blocked | Readiness pill only; **no** contract/period setup UI in posthire |
| **Export generation** | `PayrollInputExport@1.0.0` CSV; fingerprint; idempotent replay; supersede on drift; `vendor_claimed=false` synthetic CSV | Yes — Generate / Download |
| **Upload / import** | Mirror-only `PayrollResultImport`; match/unmatch; replace with audit reason; idempotent | Yes — Upload / Replace |
| **Quarantine** | Soft rows for malformed / unmatched / fingerprint mismatch | List only — **no resolve/reprocess** |
| **Reconciliation** | Missing/extra employees + component amount diffs → `ok \| differences` | Yes — Reconcile button |
| **Employee-level diffs** | Shown under import detail | Yes, technical |
| **Fingerprint drift** | Re-export supersede; import 409 if stale | Toasts exist |
| **Run history / audit** | Exports, imports, adapter events | Yes |
| **Imported payslips** | Wave 3 docs from `import_run_id` — not payment authority | Yes, but **UUID paste** |
| **Review / close / export handoff** | Wave 4 close from `external_import`; journal **drafts**; bank **contract validation only** | Yes, but **UUID paste** + finance-heavy |

**Hard gates that must stay on:** `money_authority=external` · `payment_processing=disabled` · `mirror_only` · `posts_payment=false` · `vendor_claimed=false` · `SYNTHETIC_ONLY` for production mutations · native non-authoritative.

**Assemble honesty gap:** ops assemble path currently packages **approved contracts**; attendance / shifts / leave arrays in the export assembly used by this workflow are **empty stubs**. The product says “export inputs”; operators will assume hours and leave are included. They are not yet.

---

## 2. Can HR/finance operate this without engineering?

**No.** A Kuwait finance/HR cycle today typically looks like:

1. Freeze headcount & contracts  
2. Pull attendance / OT / unpaid leave  
3. Send package to Menaitech / ZenHR / SAP / Oracle / bureau / accountant Excel  
4. Vendor runs G2N + PIFSS + WPS/bank file  
5. HR/finance reconcile register ↔ bank ↔ GL  
6. Exceptions → next cycle or off-cycle  

Wathefni covers **(3) file shape + (5) mirror reconcile + (6) quarantine evidence** in synthetic form. It does **not** yet cover operator setup, exception closure, or a guided “period run” narrative. Engineering (or a canary script) still owns mode flip, contract seed, and recovery from concurrency/quarantine dead-ends.

---

## 3. Confusing or incomplete workflows

1. **Two “exports” live side by side** — legacy **Timesheets** (hours → preview CSV) vs **External run** (Wave 2A packaging). Buyers will not know which is authoritative for the vendor.
2. **Setup is a cliff** — readiness says Blocked (“mode must be external”, “zero approved contracts”) with nowhere in Payroll to fix either.
3. **Fingerprint** is correct engineering language; finance hears “hash,” not “inputs changed after you downloaded the file.”
4. **Quarantine is a museum** — rows appear; nobody can acknowledge, re-map, or reprocess from UI.
5. **Export rollback UI path is broken** — adapter requires `expected_row_version`; HTTP/UI send only `reason` → concurrency failure for operators (canaries pass the token; dashboard does not).
6. **Payslip + Close handoffs paste UUIDs** — not “pick this month’s reconciled import.”
7. **Honesty tension** — “external is money authority” vs “imported amounts are not authoritative **in Wathefni**” is accurate but easy to misread as “imports don’t matter.”
8. **Reconciliation depth** — compares export contract amounts vs opaque import amounts; does **not** yet model the three horizons finance actually runs (register ↔ bank ↔ GL). That is fine while money stays external — but packaging must not pretend it closes bank/GL.
9. **`blocked` recon status** exists in schema, unused — dead concept.

---

## 4. Setup friction (buyer journey)

| Friction | Today | Buyer expectation |
|---|---|---|
| Choose external mode | Ops/canary | Admin toggle + explanation |
| Approve compensation contracts | Library/API | HR compensation workspace |
| Open pay period | Backend period helpers | Calendar “this month” |
| Know what CSV columns mean for Menaitech/ZenHR/accountant | Schema version only | Mapping sheet / sample file |
| Know hours/leave are **not** in package yet | Hidden | Explicit package contents checklist |
| Recover from failed upload | Quarantine list | Guided fix + re-upload |
| Roll back wrong export | Broken in UI | One-click with concurrency |

Until those exist, Wathefni external payroll is a **qualified engine**, not a **sellable monthly ritual**.

---

## 5. Authority / permission risks

| Risk | Assessment |
|---|---|
| Money authority leak into Wathefni | **Controlled** — CHECKs + honesty + freeze |
| Manager over-scope on exports | **Controlled** — empty scope → no employees |
| SOD (approve vs export) | **Present** in Wave 1/4; external rollback allows approve **or** manage — looser than close path |
| Team manager has `manage` without `export` | Can import/reconcile but not generate — odd for small Kuwait teams where one person does both |
| Viewer/manager read-only | OK |
| Quarantine without ownership | **Risk** — exceptions pile with no accountable closer |
| Parallel_shadow vs external copy | Modes exist; UI does not explain shadow ≠ pay |

Do **not** widen permissions to “fix” UX. Clarify roles in packaging; keep fail-closed money gates.

---

## 6. How Kuwait/GCC companies actually run this

**Common patterns (market / Wave 0B aligned):**

| Pattern | Who calculates & pays | What HRIS does |
|---|---|---|
| **In-house Menaitech / ZenHR** | Vendor payroll module | People + attendance feed; sometimes full HRIS |
| **SAP / Oracle HCM payroll** | ERP payroll | HR master + time; heavy implementation |
| **Bureau / accountant + Excel** | Firm runs nets, WPS, PIFSS | Spreadsheet in/out every cycle |
| **Hybrid** | External money; internal attendance/leave SoR | Exactly Wathefni’s intended lane |

**Recurring pain (industry + GCC):**

- Earnings/deduction **code mapping drift** (#1 integration failure)  
- Late attendance/leave after package cut → silent wrong pay  
- Unmatched new joiners / terminations mid-cycle  
- Reconcile register vs bank vs GL with no exception log  
- “Who changed inputs after export?” with no fingerprint  
- Arabic/English payslip + audit reasons for PAM/salary-change justification  

Competitors (Menaitech, ZenHR, Oracle Kuwait payroll) sell **localized G2N + PIFSS + WPS + EOS + ERP journals**. That is table-stakes **for a payroll product**. It is **not** Wathefni’s near-term wedge while money stays external.

---

## 7. Table-stakes vs differentiation

### Table-stakes (must be operable for external mode)

- Clear period run checklist  
- Package contents the buyer understands  
- Export / upload / replace with audit reason  
- Exception queue with ownership  
- Employee-level variance list  
- “Inputs changed — re-export” (fingerprint, human-labeled)  
- Audit timeline  
- Role-safe actions  

Wathefni **has most of the engine**; packaging/operability is incomplete.

### Genuine Wathefni differentiation (keep; do not dilute)

1. **People SoR + frozen SoA modules** (Attendance / Leave / Shifts / Onboarding / E360) feeding a payroll package — competitors usually own payroll and bolt HR on; Wathefni owns post-hire truth first.  
2. **Explicit money-authority honesty** — rare in GCC HR marketing; buyers distrust silent “we also calculate.”  
3. **Fingerprint + quarantine + SOD** as a **control tower**, not a second calc engine.  
4. **Kuwait bilingual ops** already in External / Payslip / Close surfaces.  
5. **Action Inbox compose lane** can later surface payroll *exceptions* without owning pay (already excludes payroll SoA from inbox canary — keep that boundary until packaging is trusted).

### Do not try to differentiate on (yet)

- Beating Menaitech/ZenHR on PIFSS/WPS filing  
- Native G2N as payment authority  
- Bank execution / AS’HAL monitoring as Wathefni claim  
- AI payroll  

---

## 8. Exact buyer-facing positioning

**One line:**

> Wathefni is the Kuwait/GCC **workforce system of record and payroll control tower**: it packages approved people, contracts, and time for your external payroll engine, then reconciles the mirror back — **it does not pay.**

**Buyers:** HR Ops lead + Finance controller (dual).  
**Anti-positioning:** Not a replacement for Menaitech/ZenHR/SAP payroll calc; not a bank; not an accountant.

**Packaging name (recommended):** **External Payroll Run** (keep) with subtitle **Control tower — your payroll system still pays.**

Avoid selling “Payroll” as if nets live in Wathefni. Sell **Run packaging & reconciliation**.

---

## 9. Recommended UX / packaging changes (no rebuild)

Prioritize packaging clarity over new rails. All stay inside frozen money posture.

| # | Change | Why | Code? |
|---|---|---|---|
| P1 | **Single Run checklist** on Overview: Mode → Contracts → Period → Package contents → Export → Vendor → Upload → Reconcile → Exceptions → Payslip docs → Close draft | Makes monthly ritual obvious | Yes (UX) |
| P2 | **Setup status panel** (read-only first): show mode, payment_processing, contract count, period; deep-link or ops playbook when blocked | Removes engineering dependency for diagnosis | Yes (UX) + ops doc |
| P3 | **Package contents honesty** — list included (contracts) vs not yet (attendance/leave/shifts) | Stops false trust | Yes (copy) |
| P4 | **Rename/separate Timesheets vs External run** — Timesheets = hours review; External = vendor package | Removes dual-export confusion | Yes (IA/copy) |
| P5 | **Humanize fingerprint** — “Input snapshot ID” + “Inputs changed since download” | Finance literacy | Yes (copy) |
| P6 | **Fix export rollback** — pass `expected_row_version` from selected export | Broken operator path | Yes (small bugfix) |
| P7 | **Import picker** for Payslips + Close (no UUID paste) | Operable handoff | Yes (UX) |
| P8 | **Quarantine triage** — acknowledge / mark resolved with audit reason (no auto money admit) | Exception ownership | Yes (narrow) |
| P9 | **CSV mapping one-pager** (EN/AR) for accountant/Menaitech/ZenHR handoff | Setup friction | Docs first |
| P10 | **Role story card** — who exports vs who imports vs who approves close | SOD clarity | Copy |

Out of scope for these changes: vendor SFTP, named schemas, bank/WPS files, remittance, AI, native authority.

---

## 10. What must stay frozen

From `PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` and Wave 2A-C:

- External remains **money authority**; native **non-authoritative**  
- `payment_processing=disabled`  
- No real vendor connector / live SFTP / `vendor_claimed`  
- No bank / WPS / AS’HAL / PIFSS remittance / EOS auto-pay / payment execution  
- No AI payroll  
- No new **money** feature wave  
- Worksheets / journal drafts / bank **contract validation only**  
- Production compensation mutation stays behind `SYNTHETIC_ONLY` until a separate real-money change-control  

---

## 11. Exact next wave (only if code is required)

**Name:** Payroll Wave 2A-D — External Run Operability (packaging UX)  
**Type:** operability / packaging — **not** a money wave  
**Prerequisite:** keep `PROD_SYNTHETIC_PAYROLL_FINAL_GO` money posture intact  

### In scope (minimal)

1. Run checklist + setup status + package-contents honesty (P1–P5)  
2. Export rollback concurrency fix (P6)  
3. Import picker for Payslip + Close (P7)  
4. Quarantine acknowledge/resolve-with-reason only (P8) — still soft, still non-money  
5. EN/AR copy + IA split Timesheets vs External run  
6. Staging + prod-synthetic qualify; residual 0; sibling freezes green  

### Explicit out of scope

- Attendance/leave/shifts **full** package fill (separate gated wave when SoA handoff is proven — do not smuggle into 2A-D)  
- Real vendor schema / connector  
- Bank/WPS/PIFSS/EOS/payment  
- Native G2N authority  
- AI  
- Broad real-employee money pilot  

### If leadership wants zero Payroll code

Ship **docs-only** first: operator playbook + CSV mapping one-pager (P9) + positioning (section 8). That reduces sales confusion but **does not** make the product operable without engineering — P6/P7 remain proven code gaps.

**Recommendation:** authorize **Wave 2A-D Operability** as the only next Payroll code wave; refuse any money reopen until operability GO.

---

## 12. Sources (internal + market)

| Tier | Sources |
|---|---|
| Product truth | `ExternalPayrollWorkspace.tsx`, `payrollExternalUx.ts`, `PayslipWorkspace.tsx`, `CloseExportWorkspace.tsx`, `payroll_external_adapter_wave2a.py`, Wave 2A/2A-C/Final freezes |
| Architecture prior | `PAYROLL_WAVE0B_KUWAIT_GCC_ARCHITECTURE_RESEARCH.md`, Wave 0 production truth audit |
| Market | Menaitech Kuwait FAQs (PIFSS/WPS/ERP); ZenHR Kuwait payroll + ERP journal integrations; Oracle Fusion Payroll for Kuwait setup docs; industry recon playbooks (HRIS↔payroll↔GL mapping drift) |

---

## Decision table

| Decision | Verdict |
|---|---|
| Keep external money authority posture | **GO** |
| Sell as payroll bureau replacement | **NO-GO** |
| Buyer packaging / control-tower positioning | **GO** |
| Wave 2A-D Operability (narrow UX) | **Conditional GO** — owner change-control |
| Fill attendance/leave/shifts into export package | **Defer** — separate gated wave |
| Vendor connector / real money / AI | **NO-GO** |
