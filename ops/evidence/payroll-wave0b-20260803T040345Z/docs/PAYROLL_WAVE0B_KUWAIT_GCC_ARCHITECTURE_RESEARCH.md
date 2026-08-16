# Payroll Wave 0B — Kuwait/GCC law, operations, competitors and long-term architecture

**Stamp:** `20260803T040345Z`  
**Mode:** research only — no code, deploy, salary calculation, or real payroll mutation  
**Prior gate:** Wave 0 `PROD_READONLY_PAYROLL_WAVE0_NO_GO`  
**Evidence:** `ops/evidence/payroll-wave0b-20260803T040345Z/`  

## Important disclaimer

This is **software-architecture research**, not legal, tax, banking, or accounting advice.

- Statutory figures below are research notes for counsel / bank / accountant confirmation.
- English translations of Law 6/2010 vary; Arabic text + counsel prevail for enforcement.
- Secondary sources (PwC, vendor marketing, payroll blogs) are used to flag ambiguity, not as product law.
- Wathefni must **not** claim automatic Kuwait payroll compliance until counsel-approved rate tables and remittance proofs exist.
- **Do not add XBRL** unless a specific proven customer/regulator requirement appears.

---

## Objective verdict

**Architecture recommendation before money authority:**

| Question | Verdict |
|---|---|
| Build full Wathefni-native gross-to-net + PIFSS + WPS + EOS in Wave 1? | **NO** |
| Define money-authority foundation that works for native **and** external modes? | **YES — Wave 1** |
| Support External Payroll as a first-class mode? | **YES** |
| Support Parallel comparison / migration? | **YES (Wave 2+)** |
| Encode Art. 51/53/66/69 as enforced calculators now? | **NO — counsel-gated** |
| XBRL | **Out of scope** (no proven requirement) |

Wathefni already owns people, attendance, leave, shifts and lifecycle. Competitors already own deep Kuwait payroll calc (PIFSS, WPS files, EOS). Wave 1 must own **contracts, periods, SOD, handoffs and export/import contracts** — not pretend to be a remitting payroll bureau.

---

## Source tiers

| Tier | Meaning | Sources used |
|---|---|---|
| **A — Primary / official** | Law texts, KGO PDFs, official English translations | Law No. 6/2010 (KGO PDF); Art. 51–56, 66, 69, 70, 80 via EN translations; Kuwait Times PAM/AS’HAL reporting |
| **B — Official-adjacent / reputable tax** | Structured secondary used for rates | PwC Tax Summaries (Kuwait individual other taxes); ILO NATLEX refs from prior KW research |
| **C — Vendor / operational** | Market practice, not law | HLB HAMT payroll guides; greytHR / Envoy AS’HAL notes; ZenHR, Menaitech, Warah, Qimma marketing; enterprise HRIS integration playbooks |
| **D — Prior Wathefni research** | Internal | `ops/KUWAIT_PRIVATE_SECTOR_REQUIREMENTS_RESEARCH.md`; Wave 0 audit |

Confidence codes: **H** high · **M** medium · **UC** uncertain / counsel required.

---

## 1. Official Kuwait legal / payroll matrix

| # | Topic | Rule (research note) | Class | Source tier | Confidence | Wathefni role now | Enforce calc? |
|---|---|---|---|---|---|---|---|
| L1 | Wage definition | Wage includes basic + contractual allowances broadly | Statutory | A Art. 55–56 | H | Store components | Later |
| L2 | Pay timing | Monthly-paid wages at least monthly | Statutory | A Art. 56 | H | Period policy | Outside rails |
| L3 | OT written order | Overtime requires employer written order; special OT record | Statutory | A Art. 66 | H | Store OT + written-order flag | Record yes |
| L4 | OT limits | ≤2 hours/day; annual/weekly caps in EN text (~180h/yr, 3 days/wk, 90 days/yr) | Statutory | A Art. 66 EN | M | Soft warn | No hard claim |
| L5 | OT ordinary premium | +25% over ordinary rate for similar period | Statutory | A Art. 66 | H | Counsel rate table | Review_only until signed |
| L6 | Weekly rest / holiday work | Guide/practice: rest-day ~150% + day off; public holiday ~200% + day off | Statutory + guidance | A/B Art. 66–67 area; Worker’s Guide | M | Company calendar + OT type | Counsel |
| L7 | Sick leave bands | Per year: 15d full · 10d ¾ · 10d ½ · 10d ¼ · 30d unpaid (75d total) | Statutory | A Art. 69 | H structure | Leave→Payroll classification | Counsel for pay fractions |
| L8 | Annual leave | 30 days; first-year eligibility **9 months** in older EN Art. 70; some secondary say 6 | Statutory | A Art. 70 vs C | **UC** | Leave module | Do not hardcode either |
| L9 | EOS monthly workers | 15 days/year first 5 yrs · 1 month/year thereafter · cap 1.5 years wage | Statutory | A Art. 51 | H structure | Settlement inputs only | No auto |
| L10 | EOS daily/hourly | 10 days/year first 5 · 15 thereafter · cap 1 year | Statutory | A Art. 51 | H structure | Same | No auto |
| L11 | Resignation EOS scale | <3y 0 · 3–5y ½ · 5–10y ⅔ · ≥10y full | Statutory | A Art. 53 | H | Termination reason | Counsel |
| L12 | Kuwaiti / PIFSS interaction | Law 17/2018 amends Art. 51 interaction for nationals | Statutory | A/B | **UC** | Category flag | Counsel |
| L13 | Labour file retention | Contract, Civil ID, work permit, leave, OT, injuries, termination | Statutory | A Art. 80 | H | Already E360/docs direction | Store |
| L14 | No personal income tax | General rule for individuals | Tax | B PwC | H | No PAYE engine | N/A |
| L15 | PAM AS’HAL wage monitoring | Electronic salary via local banks; portal monitoring; late/mismatch risk to PAM file | GP / practice | A Kuwait Times; C greytHR/Envoy | M | Evidence + export prep | Do not claim filing |
| L16 | Salary reduction justification | Operational guidance: written justification to PAM if salary reduced | GP / practice | C | M | Audit reason on adjustments | Counsel/PAM confirm |

**Separation rule:** statutory Kuwait ≠ company policy ≠ bank/accounting export ≠ manual exceptions.

---

## 2. PIFSS / GCC-national matrix

| Category | Social insurance | EOS / indemnity | Ceiling / notes | Confidence | Wathefni |
|---|---|---|---|---|---|
| **Kuwaiti national** | PIFSS mandatory | Art. 51/53 interaction via Law 17/2018 — counsel | Employer **11.5%**; employee **8%** on salary up to **KWD 2,750**/mo; additional employee **2.5%** up to **KWD 1,500**/mo (PwC) | M (rates B) | Store category + contributory salary components; **X remittance** |
| **GCC national in Kuwait** | Home-state scheme via GCC insurance-protection extension | Usually not Kuwait expat EOS path | Rates differ by home country (examples in secondary tables: UAE/SA/QA/BH/OM employer+employee %) | **UC** — confirm current PIFSS/GCC schedule | Store nationality + home scheme; **X calc** until counsel |
| **Expatriate (non-GCC)** | No PIFSS | Labour Law terminal indemnity | PwC wording conflicts with Art. 51 English (PwC cites 3-year gate / different tiers) — **do not encode PwC as law** | Structure H; formula UC | Settlement inputs; worksheet after counsel |
| **Domestic workers** | Separate regime (Law 68/2015) | Outside private-sector pack | — | M | Out of scope |

**Design rule:** Payroll engine must key off `nationality_class` ∈ {kuwaiti_national, gcc_national, expatriate_private_sector, …}. Never apply PIFSS to expats. Never claim remittance completion inside Wathefni without a proven PIFSS channel.

---

## 3. Banking / export requirements matrix

| Requirement | Nature | What Wathefni may do | What remains external | Proven? |
|---|---|---|---|---|
| Pay via local Kuwaiti bank, salary-designated transfer | GP / WPS practice | Store IBAN; produce **bank-ready file draft**; evidence log | Bank executes; AS’HAL/Shamel monitors | Practice M |
| Match transfer to work-permit / registered wage | GP | Export identity + contractual wage; flag mismatches | PAM/AS’HAL | UC exact field map |
| Timing (commonly by ~5th; enforcement windows reported) | GP | Period due-date policy; late alerts | Bank + PAM | UC exact decree text |
| Salary SIF / bank CSV formats (NBK, KFH, Boubyan, …) | Bank practice | Multi-format exporters behind adapter | Bank validation | Per-bank interview |
| Reduction / unpaid leave justification to PAM | GP practice | Adjustment reason + attachment | PAM submission | Confirm |
| Accounting journals / cost centres | Accounting | Optional journal export from closed run | ERP posts | Customer ERP interview |
| XBRL | — | **Do not build** | — | No proven need |

---

## 4. Competitor capability and gap matrix

### 4.1 Enterprise HRIS → payroll patterns

| Platform | Typical model | Integration depth | Implication for Wathefni |
|---|---|---|---|
| **SAP SuccessFactors** | EC master → native EC Payroll **or** third-party via CompoundEmployee / SFTP / MDF payslip return | Deep (SOAP/OData + file) | Customers expect **HR SoR ≠ payroll engine**; payslips can be imported |
| **Oracle HCM** | Worker/compensation REST + FBDI; Global Payroll Interface or external bureau | Deep | Same: export master + time; import results |
| **Dynamics 365 HR** | Dataverse OData payroll integration entities | Medium–Deep | Adapter-friendly |
| **Odoo** | Native payroll modules + accounting; lighter GCC localization unless partner | Medium | SME native competitor / integration target |
| **Zoho Payroll** | Cloud payroll with APIs; not Kuwait-deep by default | Medium | Useful as “external engine” pattern, not KW SoT |

Common enterprise pattern: **HRIS owns people; payroll owns gross-to-net; ERP owns GL; bank owns money movement.**

### 4.2 Kuwait / GCC payroll vendors

| Vendor | Segment (public) | Solves today (claimed) | Burden | API / integration | Gap vs Wathefni need | Interview needed? |
|---|---|---|---|---|---|---|
| **Menaitech (MenaPAY)** | Mid–enterprise GCC | PIFSS, WPS CSV, EOS/indemnity, multi-branch, retro, journals | High implementation; modular | Regional product; finance exports | Deep payroll; weaker modern recruiting/WhatsApp | Yes — API + bank formats |
| **ZenHR** | SME–mid GCC (~public ~$3/ee claims) | PIFSS, EOSB, bilingual, Dynamics/QuickBooks/Odoo/Xero links | Lower than Menaitech | Accounting integrations marketed | Strong local payroll; not Wathefni pre-hire depth | Yes — export/import contract |
| **Warah** | Kuwait SME–growth | Attendance, leave, payroll, WPS files (NBK/KFH/Boubyan…), EOS | Newer platform | Bank formats claimed | Overlaps Wathefni post-hire | Yes — maturity / API |
| **Qimma** | Kuwait SME (new, 2025) | KW law automation, indemnity, social security, bank files, journals | Early | Open API + Zapier claimed | Unproven scale; marketing-heavy compliance claims | Yes — real customer proof |
| **Bayanat / Bayzat-like** | Benefits / multi-GCC | Benefits stronger than KW-deep payroll (varies by product) | Medium | Partner ecosystems | Not a full KW payroll substitute by default | Segment-dependent |
| **Payroll bureaus (HLB etc.)** | Outsourced calc + remittance | Full compliance ops | Service contract | File-based | Wathefni stays HR + evidence | Yes — SFTP schema |

### 4.3 What competitors already solve (Wathefni should not rush to duplicate)

1. PIFSS contribution engines and remittance packs  
2. Bank WPS / salary SIF generation for multiple Kuwaiti banks  
3. Opinionated EOS calculators (often marketed as “fully compliant” — still counsel risk)  
4. Retro / arrears payroll transactions  
5. Accounting journal packs into common ERPs  

### 4.4 What competitors do **not** own (Wathefni advantage)

1. Pre-hire → offer → onboarding → employee 360 continuous identity  
2. Attendance authority + leave workflow already frozen as no-money handoffs  
3. Shifts enterprise scheduling with explicit no-money boundary  
4. WhatsApp / bilingual operator surfaces tied to the same employee key  
5. Controlled rollout / freeze discipline across modules  

---

## 5. Customer-segment strategy

| Segment | Likely payroll posture | Wathefni mode | Why |
|---|---|---|---|
| **SME, no payroll software** | Spreadsheets / accountant | Native (phased) or External bureau | Need simple contracts → timesheets → payslip → bank file |
| **SME on ZenHR / Warah / Qimma** | External engine | **External** (default) | Do not rip-and-replace; Wathefni = HR + scheduling + evidence |
| **Mid-market on Menaitech** | Deep local payroll | External / Parallel | Integrate; migrate only if customer asks |
| **Enterprise on SAP/Oracle/D365** | Global payroll or local bureau | External | Wathefni is post-hire Kuwait ops layer; payroll stays corporate |
| **Multi-entity / multi-country** | Mixed | External + Parallel | Native KW calc optional later per legal entity |

**Go-to-market rule:** sell Wathefni as **Kuwait workforce authority** (people, time, leave, shifts, compliance evidence). Sell Payroll as **modes**, not a forced rip-replace of Menaitech/ZenHR.

---

## 6. Three operating modes

### Mode A — Wathefni-native Payroll

| Dimension | Spec |
|---|---|
| **Canonical authority** | Wathefni closed payroll run is money authority for that legal entity |
| **Compensation ownership** | Wathefni effective-dated salary contracts / components |
| **Period/run ownership** | Wathefni pay periods + run versions |
| **Inputs** | Approved attendance snapshots, leave classifications, shifts scheduled, contracts, nationality class |
| **Outputs** | Payslips, bank-file drafts, journal drafts, PIFSS worksheets (later) |
| **Approval / SOD** | Draft → review → approve → export; `manage` ≠ `export`; no self-approve |
| **Payslip ownership** | Wathefni generates and stores |
| **Bank/export ownership** | Wathefni generates files; bank/AS’HAL remain external |
| **Reconciliation** | Run totals vs bank confirmation vs PAM portal evidence |
| **Failure / rollback** | Soft-close only; reverse via new adjustment run; never silent rewrite of posted run |
| **When** | After Wave 1 foundation + counsel-gated Wave 2+ calcs |

### Mode B — External Payroll

| Dimension | Spec |
|---|---|
| **Canonical authority** | External system’s posted run (ZenHR / Menaitech / SAP / bureau) |
| **Compensation ownership** | **Preferred:** Wathefni contracts push to external; or external owns and Wathefni mirrors read-only |
| **Period/run ownership** | External; Wathefni stores `external_run_id` + status mirror |
| **Inputs Wathefni → external** | Employee master delta, IBAN, contracts, approved hours, unpaid leave handoffs, terminations |
| **Outputs external → Wathefni** | Payslip PDF/lines, net/gross, deductions, employer cost, payment status |
| **Approval / SOD** | Approvals may live externally; Wathefni still gates **time approval** and export of inputs |
| **Payslip ownership** | External generates; Wathefni displays imported copy |
| **Bank/export ownership** | External (usual) |
| **Reconciliation** | Wathefni input fingerprint vs external result hash; exceptions queue |
| **Failure / rollback** | Re-export inputs; never invent money; quarantine failed imports |
| **When** | **Default for customers with existing payroll** |

### Mode C — Parallel comparison / migration

| Dimension | Spec |
|---|---|
| **Canonical authority** | Explicitly **external** until cutover gate flips |
| **Compensation ownership** | Dual-write or push from Wathefni contracts into both |
| **Period/run ownership** | Both run same period; Wathefni marks `parallel_shadow` |
| **Inputs / outputs** | Same inputs to both; compare nets/lines/EOS |
| **Approval / SOD** | External remains payment authority; Wathefni shadow cannot export bank files |
| **Payslip ownership** | External for employees; Wathefni shadow for HR compare only |
| **Bank/export ownership** | External only |
| **Reconciliation** | Line-level diff report; tolerance rules; sign-off |
| **Failure / rollback** | Shadow discard; no payment impact |
| **When** | Migration Wave after External stable |

---

## 7. What Wathefni must own vs remain external

### Must own (all modes)

1. Employee canonical identity and lifecycle  
2. Effective-dated **compensation contracts** (base + allowances + deductions metadata)  
3. Attendance / leave / shifts **input authority** already frozen  
4. Pay **period** calendar and lock semantics  
5. Timesheet / hours approval + SOD  
6. Audit trail, consent for sensitive pay data, employee visibility gates  
7. Adapter contracts: `PayrollInputExport` / `PayrollResultImport`  
8. Honesty flags: `payment_processing`, `money_authority_mode`, `external_system`  

### Should remain external (near term)

1. PIFSS remittance / portal filing  
2. Bank execution and AS’HAL monitoring  
3. Opinionated EOS auto-pay until counsel-signed worksheet  
4. Full gross-to-net for complex enterprise (optional Native later)  
5. ERP journal posting (export only)  
6. XBRL  

### Company-configurable (not statutory hardcode)

- Absence / late / early deduction policy  
- OT paid vs review_only vs capped  
- Pay cycle day and cutoffs  
- Allowance catalogues beyond contractual minimum  
- Cost-centre mapping  

### Manual exceptional cases

- Mid-cycle corrections with dual control  
- Ex-gratia / management adjustments  
- Court/PAM ordered amounts  
- Historical arrears from pre-Wathefni systems  

---

## 8. Exact Payroll Wave 1 scope

**Name:** Payroll Wave 1 — Money-authority foundation (mode-agnostic, no payment)

**In scope**

1. Effective-dated **salary contract / component ledger** seeded from accepted offer terms (no silent derivation into net pay).  
2. First-class **pay period** entity (open → locked → closed) replacing “export exists ⇒ lock”.  
3. Hard bans: timesheet self-approval; fix SOD to real `payroll.manage` × `payroll.export` (or introduce wired `payroll.approve`).  
4. Attendance handoff truth for real subjects (controlled snapshots or explicit legacy freeze honesty).  
5. Mode flag: `native | external | parallel_shadow` with honesty payload.  
6. **External adapter stub:** versioned `PayrollInputExport` schema (employee, contract, hours, leave classifications) — file/API contract only; no live customer cutover required.  
7. Quarantine May 2026 smoke timesheets.  
8. Keep `payment_processing=disabled`; no bank files, payslips as money, PIFSS calc, EOS auto, journals, XBRL.  
9. Evidence pack + freeze gates vs E360 / Onboarding / Attendance / Leave / Shifts.

**Out of scope for Wave 1**

- Gross-to-net  
- PIFSS contribution math  
- WPS/AS’HAL file generation for production banks  
- EOS calculator product claim  
- Employee payslip delivery as pay advice  
- Accounting postings  
- Any change that weakens frozen modules  

**Qualification steps (estimated)**

1. Local schema + unit/smoke for contracts, periods, SOD  
2. Staging synthetic canary (create contract → period → hours → lock; no money)  
3. External export schema golden-file tests  
4. Prod controlled read-only posture check (still no payment)  
5. Sibling freeze regressions  
6. Owner review of mode strategy  

---

## 9. Phased roadmap

| Wave | Goal | Modes | Money? | Qualification |
|---|---|---|---|---|
| **0** | Production truth | — | No | Done — NO-GO money |
| **0B** | Law / competitors / architecture | All modes defined | No | This document |
| **1** | Foundation: contracts, periods, SOD, adapter stub | Mode flag only | No payment | Staging synthetic + freeze suite |
| **2A** | External live adapter (one vendor or bureau SFTP) | External | External posts | Parallel dry-run one period |
| **2B** | Native preview amounts (hourly/monthly) with policy version provenance | Native preview | Preview only | Counsel sign-off on OT/leave flags still review_only |
| **3** | Payslip import (external) or generate preview payslip (native) | Both | Display only | Employee-app canary |
| **4** | Bank-file draft + evidence pack | Native/External | Draft only | Bank format interview + sandbox |
| **5** | PIFSS worksheet + remittance checklist | Native later | Worksheet | Counsel + PIFSS channel proof |
| **6** | EOS counsel worksheet | Native | Worksheet | Counsel + Law 17/2018 check |
| **7** | Parallel cutover tooling | Parallel → Native or stay External | Controlled | Two consecutive matching periods |
| **∞** | XBRL | — | — | Only if proven requirement |

---

## 10. Unresolved questions (block encoding)

### Legal counsel

1. Confirm Art. 70 first-year leave eligibility (6 vs 9 months) current Arabic text.  
2. Confirm Art. 51/53 EOS after Law 17/2018 for **Kuwaiti** employees with PIFSS.  
3. Resolve conflict between PwC expat indemnity summary and Art. 51 EN translation.  
4. Confirm Art. 69 sick-leave wage base (basic only vs wage with allowances).  
5. Confirm rest-day / holiday OT premiums and compensatory day rules for product tables.  
6. Confirm whether unpaid sick-leave days affect EOS service length (secondary claims diverge).  

### Banks / PAM ops

7. Exact AS’HAL / Shamel field map and current enforcement dates for the customer’s bank.  
8. Per-bank salary file layouts (NBK, KFH, Boubyan, others).  
9. Required justification letter format for salary reductions / unpaid leave.  

### Accountants / ERP

10. Preferred journal shape (summary vs employee lines) and cost-centre dimensions.  
11. Rounding convention for KWD fils (3 dp) on OT/sick fractions.  
12. Retro/arrears posting periods vs prior closed months.  

### Customer interviews

13. Which payroll engine is already live (Menaitech / ZenHR / Warah / Qimma / SAP / bureau / Excel)?  
14. Who is money authority today (HR, finance, outsourcer)?  
15. Do they need Wathefni-native payslips or only HR + time feeding external payroll?  
16. Multi-entity / multi-IBAN / multi-cost-centre complexity?  
17. Appetite for Parallel shadow before any Native cutover?  

---

## 11. Freeze / safety reminders

- Wave 0 production remains **NO-GO** for money.  
- Attendance / Leave / Shifts freezes: no payroll money mutation from those modules.  
- Lifecycle settlement packets stay inputs-only.  
- `payment_processing=disabled` stays hard-forced until a later owner-approved wave.  
- No XBRL workstream.

---

## 12. Gate

`PROD_RESEARCH_PAYROLL_WAVE0B_ARCHITECTURE_GO`

Research complete. Implementation must start at **Wave 1 foundation**, not at native PIFSS/WPS/EOS.
