# Kuwait Private-Sector HR Requirements Research

**Date:** 2026-07-25  
**Mode:** research only — no code, migration, deploy, or country-pack implementation  
**Compared against:** `ops/KUWAIT_GCC_COUNTRY_PACK_READINESS_AUDIT.md`  
**Scope:** Kuwait **private / civil sector** employment relevant to Wathefni HR software  

---

## Important disclaimer

This document is **software-requirements research**, not legal advice.

- Wathefni must **not** claim automatic Kuwait legal compliance.  
- Statutory figures below are **research notes** for counsel review; they are **not** ready to encode as enforced product rules.  
- Government service document lists describe **what is needed to complete a transaction**, not what must live permanently in an HR employee master.  
- Direct fetches of some `e.gov.kw` pages returned gateway 403/500 during this research window; those pages are still cited from Kuwait Government Online listings and search-indexed official summaries, with **confidence noted**.

---

## Source tiers

| Tier | Meaning | Examples used |
|---|---|---|
| **A — Primary / official** | Kuwait law, official English translation, ILO NATLEX, Kuwait Government Online service pages, PAM site | Law No. 6/2010 (NATLEX KWT-2010-L-83616; KGO PDF); Law No. 17/2018 (NATLEX); KGO MOI Article 18 / first residence / PACI first registration listings; `manpower.gov.kw` employment services |
| **B — Official guidance republished** | Worker guides citing Law 6/2010 article numbers | Kuwait HR Worker’s Guide PDF (2024-09-11, cites Arts 28–70, 66, etc.) |
| **C — Secondary** | Law firms, payroll vendors, expat guides | PwC Tax Summaries; Al Tamimi / Ogletree notes; commercial HR blogs | Used **only** to flag ambiguity or counsel questions |

**Terminology rule used in this report (official KW English):**

| Prefer | Avoid in product copy |
|---|---|
| Residence permit / residency (إقامة) | Saudi-style **iqama** as the canonical term |
| Civil ID (البطاقة المدنية) — PACI | Treating Civil ID as “visa” |
| Work permit (إذن العمل) — PAM | Collapsing work permit into residence |
| Article 18 — private/civil sector residence | Using Article 22 (family) as a default employee work category |

Colloquial “iqama” appears widely in secondary English; **official KGO pages say residence / Article 18**. Product ids such as `residency_iqama` should be retired or aliased away from Saudi naming.

---

## Research method limits

| Limit | Impact |
|---|---|
| Live `e.gov.kw` / `paci.gov.kw` fetches sometimes blocked | Service document lists taken from KGO-indexed content + secondary corroboration; **confirm on Sahel / Ashal before pilot go-live** |
| English translations of Law 6/2010 vary | Prefer Arabic text + counsel for enforcement; English used for product scoping |
| Amendments (e.g. annual-leave eligibility months; Art. 51 / PIFSS) | Multiple secondary sources disagree with older English Art. 70 “nine months”; **counsel must confirm current text** |
| Exit-permit / 2025 travel rules | Reported in secondary sources; **not used as pilot software P0** until confirmed on official MOI/PAM channels |

---

## 1. Requirement catalogue

For each item: **requirement → category → source → confidence → nature → Wathefni role → needed before first pilot?**

Nature codes: **LR** legally required · **GP** government-process required · **CP** common employer practice · **OP** optional employer policy · **UC** uncertain / counsel  

Wathefni role codes: **S** store · **V** validate · **R** remind · **C** calculate · **A** audit · **X** outside platform  

### 1.1 Employer and legal-entity records

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| E1 | Employer must be a Kuwait-registered entity able to hire (commercial licence / CR) | All private employers | GP: MOCI commercial licence; C: formation guides | Medium (GP chain clear; exact field set UC) | GP | S registered name + CR/licence refs as **employer-supplied**; V format only; X MOCI filing | Yes if hiring anyone |
| E2 | PAM employer file required before sponsoring expatriate work permits | Employers hiring expats | GP: PAM / Ashal practice; C: PAM registration guides | Medium–High | GP | S PAM file number (text); X open/maintain PAM file | Yes **if** expat hires; else No |
| E3 | Signature authorization / authorized signatory for MOI/PAM forms | Sponsoring employers | A: KGO MOI private-sector entry visa & Article 18 residence document lists | Medium (page content via KGO index) | GP | S authorized signatory name (already on offers); X government forms | Useful; not blocking nationals-only |
| E4 | Kuwaitisation / quota constraints on foreign hiring | Employers hiring expats | C: PAM quota commentary | Low–Medium | GP + UC | X enforcement; optional S note | No for software P0 |
| E5 | Distinct employing legal entity vs Wathefni `company_code` tenant | Multi-entity groups; PAM sponsorship | Operational + Art. 28 lodging with competent authority | High for multi-entity; Medium for single-entity pilot | CP / architecture | S minimal legal-entity master | **Yes** (even single entity: one default entity) — see §4 |

### 1.2 Employee identity (Kuwaiti vs expatriate)

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| I1 | Civil ID exists for residents (citizens and expatriates) | All residents | A: PACI role; KGO PACI first-time registration | High | LR/GP | S civil_id_number (sensitive); S/R expiry; A access; V checksum only if counsel-approved algorithm | Yes |
| I2 | Nationality recorded for workforce classification (Kuwaiti / GCC / other) | All employees | Operational; PIFSS vs EOS pathways (C: PwC) | High need; medium legal mapping | CP + UC for GCC edge cases | S nationality / nationality_class | Yes |
| I3 | Passport number + expiry for expatriates | Expats | A: KGO MOI residence docs require original passport; Art. 80 file may include submitted docs | High | GP | Prefer **document metadata** + optional confirmed fields; R expiry | Yes if expats |
| I4 | Residence article / type (Art. 18 for private-sector workers) | Expats on work residence | A: KGO “Article (18) … Foreigners' Residence Law” | High | GP | S `residence_article` enum starting with `article_18`; do not default Art. 20/22 for employees | Yes if expats |
| I5 | Distinguish Kuwaiti nationals (no Art. 18 work residence) from expats | Nationals | Residence law structure + Labour Law scope | High | LR/GP | S `employee_category`: `kuwaiti_national` \| `expatriate_private_sector` \| … | Yes |
| I6 | Police clearance, blood type, lease, fingerprint notice | Expat first residence / PACI registration | A: KGO MOI Art. 18 / PACI first registration lists | Medium | GP **transaction** docs | **X permanent master**; optional transient onboarding checklist items only | No as master fields |
| I7 | Health insurance certificate | Expat residence issuance/renewal | A: KGO Art. 18 document lists | Medium | GP | Optional S/R as document; X insurance purchase | Pilot optional |

### 1.3 Civil ID, passport, residency, work permit

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| D1 | Employer labour file must include **copy of Civil ID** | All private-sector workers | A: Law 6/2010 **Art. 80** (English translation) | High | LR | S document + link to civil_id_number; R renewal | Yes |
| D2 | Employer labour file must include **copy of work contract** | All | Art. 80 | High | LR | S signed contract document | Yes |
| D3 | Employer labour file must include **copy of work permit** | Workers who have a work permit (typically expats) | Art. 80 | High | LR | S work_permit document + number/expiry as metadata; R | Yes if expats |
| D4 | Work permit issued/managed via PAM | Expats | A: KGO “Applying for a Work Permit” (PAM); MOI visa requires work permit in system | High | GP | X PAM portal actions; S copies + dates HR holds | Track only |
| D5 | MOI issues / renews / cancels **private residence Article 18** | Expats | A: KGO Private Residence Article 18 service family | High | GP | X MOI/Sahel; S residence stamp/permit copy + expiry; R | Track only |
| D6 | PACI Civil ID first registration after residency stamp; late fee if > ~1 month | Expats | A: KGO PACI “First Time Registration of Expatriates” (fine **20 KD** if after one month — indexed content) | Medium (confirm current fee on Sahel) | GP | R deadline after residency_start; X pay fine / register | Remind only |
| D7 | Medical fitness / disease-free certificate | Expats first residence | A: KGO MOI first residence / Art. 18 lists; MOH clinics in practice | Medium | GP | Optional document; R if employer tracks; X medical exam | Optional pilot |
| D8 | Do **not** treat every MOI/PACI attachment as HR master identity | All | Research principle + Art. 80 limited list | High | OP/architecture | Keep transaction docs out of identity schema | Yes (design rule) |

### 1.4 Article 18 and other residence categories

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| A1 | **Article 18** = private/civil sector employee residence | Private-sector expats | A: KGO first residence “pursuant to Article (18)” | High | GP | Primary expat employment category | Yes if expats |
| A2 | **Article 17** = government sector residence | Public employers | A: KGO Govt Residence Article 17 | High | GP | Out of private-sector pack scope | No |
| A3 | **Article 22** / family residence | Dependents | A: KGO family join / transfer listings | High | GP | Not default employee work status; optional later | No for pilot |
| A4 | Domestic workers (separate regime) | Domestic | C: Law 68/2015 references | Medium | LR separate | **Outside** private-sector pack | No |

### 1.5 Onboarding documents (HR vs government)

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| O1 | Signed employment contract in employee file | All | Art. 28, 29, 80 | High | LR | S | Yes |
| O2 | Civil ID copy in file | All (once issued) | Art. 80 | High | LR | S | Yes |
| O3 | Work permit copy in file | Expats | Art. 80 | High | LR | S | If expats |
| O4 | Passport copy | Expats | CP + GP applications | Medium | CP/GP | S document; not always permanent master number | If expats |
| O5 | Personal photo | PACI/MOI process + HR practice | KGO PACI photos; CP | Medium | CP/GP | S | Optional |
| O6 | Bank / IBAN for salary | Payroll practice | CP; banks require Civil ID | Medium | CP | S | Yes for paid employees |
| O7 | Attested education certificates | Some PAM roles | C: role-dependent | Low–Medium | GP/UC | Transient checklist; not universal master | No universal |
| O8 | Emergency contact, policy acks | Employer | OP | High | OP | S | Optional |

### 1.6 Employment contracts and retention

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| C1 | Contract in writing with signing date, effective date, wage, term (if limited), nature of work | All | Art. 28 | High | LR | S terms + document; V presence of required fields in **employer template** (not invent law text) | Yes |
| C2 | **Arabic** text prevails; other languages may be added | All | Art. 29 | High | LR | S `document_language`; support AR upload; do not claim EN-only PDF is the legal original | Yes |
| C3 | Three copies; one lodged with competent authority | All | Art. 28 | High | LR/GP | X lodging with PAM/authority; S employer + employee copies; A “lodged?” checklist optional | Track lodging as checklist, not auto-file |
| C4 | Keep labour file contents per Art. 80 | All | Art. 80 | High | LR | S listed artifacts; A retention | Yes |
| C5 | Return employee documents at end of service | Leavers | Art. 54 | High | LR | Checklist + A | Soft offboard P1 |

### 1.7 Probation

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| P1 | Probation, if used, ≤ **100 working days**; once per employer | All | Art. 32 | High | LR | S `probation_end_date` / days; V ≤100 working days **as soft warning** until counsel enables hard block | Snapshot from offer; soft validate |
| P2 | Either party may terminate without notice during probation; employer-paid EOS for period worked if employer terminates | All | Art. 32 | High | LR | X auto-calc EOS; S status reason | Counsel for calc |

### 1.8 Working hours, rest days, overtime

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| H1 | Normal hours framework (commonly 8/day, 48/week; Ramadan reduction) | All | Art. 64–65 area; B: Worker’s Guide | Medium–High (exact article mapping for product UC) | LR | S attendance; employer policy for schedules; **no auto “illegal hours” claims** without counsel | Attendance store yes; enforce law No |
| H2 | Paid weekly rest (guide: 24h after 6 workdays) | All | B: Worker’s Guide citing law | Medium | LR | Employer calendar; OP which days are rest | Policy |
| H3 | Overtime only with written order; limits; premium **+25%** ordinary; weekly rest / holiday premiums in guide | All | Art. 66; B: Worker’s Guide (+25% / +50% / 100%) | Medium–High for existence; UC for edge cases | LR | S OT minutes + written-order flag; C **only** after counsel-approved rate table; else review_only | Store/remind; calc later |
| H4 | Special OT record | All | Art. 66 (employer shall keep OT record) | High | LR | S/A OT log (Wathefni attendance/payroll preview already close) | Yes as record-keeping |

### 1.9 Leave

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| L1 | Paid annual leave **30 days** (working-day treatment UC after amendments) | All | Art. 70; B: Worker’s Guide; C: Law 85/2017 notes on weekends/holidays not counting | Medium (amendments) | LR | S requests; seed policy **inert**; C only after counsel | Requests yes; enforce No |
| L2 | First-year eligibility months (**9 months in older English Art. 70**; **6 months in some secondary notes**) | All | Art. 70 EN vs C: Ogletree 2018 | **UC** | UC | Do **not** hardcode either | Counsel |
| L3 | Graduated sick leave bands | All | Art. 69 | Medium (bands in EN translation) | LR | Structure only; empty rates until counsel | No enforce |
| L4 | Maternity 70 days paid (+ unpaid care leave option) | Female employees | Art. 24 | Medium–High | LR | Later leave type; not pilot P0 | No |
| L5 | Public holidays employer calendar | All | Law + decrees | Medium | LR/OP | Employer-maintained calendar | Optional |

### 1.10 Attendance records

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| T1 | Keep OT / leave / related records in labour file | All | Art. 80, 66 | High | LR | S attendance & leave docs | Yes |
| T2 | Absence reporting to PAM (employer service) | Expats / PAM-registered | A: `manpower.gov.kw` employment services describe employer absence registration | Medium | GP | X PAM absence filing; optional mirror note | No |

### 1.11 Payroll inputs, allowances, deductions

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| $1 | Wage elements defined broadly (basic + contractual allowances) | All | Art. 55–56 | High | LR | S salary + allowances from offer/contract | Yes store |
| $2 | Monthly pay at least monthly for monthly-paid | Monthly-paid | Art. 56 | High | LR | X payment rails; S pay cycle policy | Outside pay |
| $3 | **PIFSS** contributions for Kuwaiti (and eligible) nationals | Kuwaiti employees | C: PwC Tax Summaries; Law 17/2018 Art. 51 interaction | Medium | LR | X remittance to PIFSS; optional S contribution flags later | No calc in pilot |
| $4 | Expats generally **not** in PIFSS; EOS instead | Expats | C: PwC | Medium | LR | Do not apply PIFSS calc to expats | Design rule |
| $5 | No personal income tax (general) | All | C: PwC | Medium | — | X tax engine | N/A |

### 1.12 Termination, notice, settlement, EOS

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| X1 | Unlimited contract notice: **3 months** monthly-paid / **1 month** others | Unlimited contracts | Art. 44 | High | LR | S notice dates; C pay-in-lieu only after counsel | Soft track |
| X2 | Terminal service indemnity formulas | Leavers | Art. 51–53; amended by Law 17/2018 for Kuwaiti/PIFSS interaction | Medium (formulas + amendments) | LR | **X auto-EOS product claim**; optional worksheet after counsel | No auto |
| X3 | End-of-service certificate + return documents | Leavers | Art. 54 | High | LR | Checklist | P1 |
| X4 | Cancel / transfer residence & work permit | Expat leavers | A: KGO Art. 18 cancel/transfer services | High | GP | Checklist only; X MOI/PAM | Checklist |
| X5 | Soft `employment_status=left` with audit | All | Product + Art. 80 termination date/reason | High | CP/LR hybrid | S/A | Yes |

### 1.13 Document expiry and renewal

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| R1 | Track Civil ID / residence / work permit / passport expiry | Relevant workers | Art. 80 + GP renewals | High operational | CP + GP | S/R | Yes |
| R2 | Display statutory fines (e.g. residency late fine KD/day) | Expats | Internal KW.json; C blogs | **Low** for auto amounts | UC | **Do not auto-assert fines**; optional employer-configured alert text after counsel | No |
| R3 | Remind PACI registration window after residency stamp | New expats | KGO PACI late fee note | Medium | GP | R | If expats |

### 1.14 Privacy and access controls

| # | Requirement / operational need | Category | Source | Confidence | Nature | Wathefni | Pilot? |
|---|---|---|---|---|---|---|---|
| Z1 | Civil ID and passport are sensitive identifiers | All | Operational sensitivity; Art. 80 retention | High | CP / privacy law UC | S encrypted/restricted; A access; permission gates | Yes |
| Z2 | Limit who can view Civil ID images/numbers | HR subset | CP + privacy UC | Medium | OP/UC | RBAC already directionally correct | Yes |
| Z3 | Data-processing agreement with client for Civil ID | Client | UC Kuwait privacy framework | UC | UC | Legal/commercial | Yes (commercial) |

### 1.15 Track in Wathefni vs government transactions (must not claim)

| Employer action Wathefni **may** track | Government transaction Wathefni **must not** claim to perform |
|---|---|
| Collect/store copies of Civil ID, contract, work permit, residence evidence | Issue/renew/cancel work permit (PAM/Ashal) |
| Remind expiry / PACI registration window | Issue/renew/cancel residence (MOI/Sahel) |
| Record probation, notice, leave requests, OT hours | Register Civil ID (PACI) |
| Checklist “contract lodged with authority?” | Lodge contract with competent authority |
| Checklist absence of employee for HR | Official PAM absence report filing |
| Store IBAN for payroll prep | Pay salaries through WPS/bank rails (if/when applicable) |
| Offboard status + return-docs checklist | Residence cancellation / exit procedures |
| Snapshot offer terms into employee file | Attest educational certificates / embassy legalization |

---

## 2. Comparison to readiness audit P0s

Audit software P0s from `ops/KUWAIT_GCC_COUNTRY_PACK_READINESS_AUDIT.md` §6:

| Audit P0 | Research verdict | Notes |
|---|---|---|
| **1. Offer → employee country-pack snapshot** | **Confirmed but model needs adjustment** | Snapshot **employment applicability + contract terms**, not a marketing “pack” label alone. Must include: country, legal_entity_id, currency, base wage/allowances, probation_days, start date, accepted offer id/version, template/policy versions, effective date, `document_language`. |
| **2. Unify residency vocabulary / drop iqama naming** | **Confirmed as designed** (terminology) | Official KW English: residence / Article 18. Rename `residency_iqama` → `residence_permit` (or `residency`). Keep Saudi iqama out of KW pack. |
| **3. First-class legal-entity master** | **Confirmed but model needs adjustment** | Needed as **employing entity** for Art. 28/80 and PAM sponsorship identity. Pilot fields: registered name (AR/EN), country, commercial registration / licence numbers (**employer-supplied text**), optional PAM file number, status. **Not** required: live MOCI/PAM API verification, full shareholding graph. |
| **4. Civil ID / nationality / residence article as employee fields** | **Confirmed but model needs adjustment** | **Authoritative fields:** nationality class, civil_id_number (sensitive), residence_article (expats), employment category. **Document metadata / files:** passport image, residence stamp image, work permit image, medical certificates. Do **not** promote police clearance / blood type / lease into master identity. |
| **5. Arabic document path clear** | **Confirmed as designed** | Art. 29 Arabic prevails → AR upload path is legally aligned; EN-only generated PDF must not be sold as the governing contract. |
| **6. Residency/work-permit onboarding↔compliance dual-write** | **Confirmed if pilot includes expats**; **unnecessary for nationals-only first pilot** | Art. 80 requires work-permit copy for workers who have one. Split pilot scope. |
| **7–10 Legal/policy P0s** (counsel leave; doc set; OT/weekends; no compliance claims) | **Confirmed as designed** | Reinforced by Art. 70 eligibility ambiguity and Art. 51 amendments. |

### Validation answers (explicit)

**Is a first-class legal-entity master needed?**  
**Yes, minimally.** Even a one-entity Kuwait pilot should record the employing legal person separately from the Wathefni tenant code, because MOI/PAM and Art. 28 speak to the **employer entity**, and future multi-entity groups will otherwise corrupt sponsorship and contract provenance. Identifiers: registered name AR/EN, MOCI commercial registration / licence references (text), optional PAM employer file number (text), country=`KW`, status, audit.  

**Which identity fields are authoritative vs document metadata?**  

| Authoritative employee fields | Document / metadata |
|---|---|
| `employee_category` (kuwaiti_national / expatriate_private_sector / …) | Passport scan |
| `nationality` (ISO country) | Residence permit / stamp scan |
| `civil_id_number` (sensitive) | Work permit scan |
| `civil_id_expires_on` | Medical fitness PDF |
| `residence_article` (expats; default Art. 18) | Police clearance (transient) |
| `residence_expires_on` (expats) | Blood type / lease (PACI process — transient) |
| `work_permit_number` / `work_permit_expires_on` (expats; may live on doc record) | Education attestations (role-specific) |
| `passport_number` / `passport_expires_on` (optional confirmed fields) | |

**Correct residency terminology:**  
Use **residence permit / residency (إقامة)** and **Article 18** for private-sector work residence. Do not use **iqama** as the canonical product term.

**What must snapshot from accepted offer at hire?**  
country_of_employment, employing_legal_entity → `legal_entity_id`, currency, base_salary, allowances, proposed_start_date → start_date, probation_days, document_language, template_id/version, employer_policy_version, configuration_effective_date, accepted offer_id + version, authorized_signatory (reference).  

**Different applicability for nationals vs expats?**  
**Yes.** Nationals: Civil ID + contract + (later) PIFSS pathway; no Art. 18/work permit. Expats: + passport, Art. 18 residence, work permit, medical/insurance process tracking, PAM-linked lifecycle.  

**Minimum viable document set for first private-sector pilot:** see §6.

---

## 3. Unsupported assumptions removed

| Assumption in prior audit / product | Research disposition |
|---|---|
| “Iqama” is correct Kuwait canonical term | **Removed** — use residence / Article 18 |
| Article 20/22 are core private-sector employee categories | **Removed from pilot defaults** — family/dependent; not employee work residence |
| Every MOI/PACI application attachment belongs in HR master | **Removed** |
| KW.json fine_per_day_kd is safe to display as law | **Removed** until counsel + current official fee schedule |
| Annual leave first-year gate is safely “6 months” or “9 months” in code | **Removed** — **UC** |
| Wathefni should calculate EOS / PIFSS for pilot | **Removed** from software P0 |
| Legal-entity master must integrate MOCI/PAM APIs | **Removed** for pilot — text identifiers suffice |
| Full country-pack registry required before first client | **Softened** — hire snapshot + entity + identity + docs first; pack registry can be P1 |
| Attendance product must encode statutory OT multipliers immediately | **Removed** — record OT; counsel before premiums |

---

## 4. Verified minimum data model (pilot)

```text
Company (tenant)
  company_code, country=KW, timezone, currency=KWD

LegalEntity
  legal_entity_id
  company_code
  registered_name_en / registered_name_ar
  country_code = KW
  commercial_registration_no   # employer-supplied
  commercial_license_no        # employer-supplied (if distinct)
  pam_employer_file_no         # optional; required operationally if hiring expats
  status
  audit

Employee
  employee_key, company_code, legal_entity_id
  employee_category            # kuwaiti_national | expatriate_private_sector | other
  name, phone, email
  nationality
  civil_id_number              # sensitive
  civil_id_expires_on
  residence_article            # null for nationals; article_18 for typical private expats
  residence_expires_on         # expats
  passport_number?             # optional confirmed
  passport_expires_on?
  start_date
  probation_end_date?          # if probation used; ≤100 working days soft-check
  employment_status            # active | left
  hire_snapshot_json           # immutable copy of offer governance + pay terms
  audit

EmployeeDocument (Art. 80 oriented)
  type: employment_contract | civil_id | work_permit | residence_permit | passport | other
  file, issued_on, expires_on, number?, source
  NOT: police_clearance | blood_type | lease as core types for pilot
```

---

## 5. Verified first-client document matrix

### Pilot A — Kuwaiti nationals only (smallest)

| Document | Store? | Remind expiry? | Master field? |
|---|---|---|---|
| Signed employment contract (Arabic original) | Required | N/A | Terms in hire_snapshot |
| Civil ID copy | Required | Yes | civil_id_number + expiry |
| Personal photo | Optional | No | No |
| Bank IBAN | Required if paid via bank | No | Yes (payroll prep) |
| Passport / residence / work permit | N/A | — | — |

### Pilot B — Mixed / expatriate private-sector (Art. 18)

All of Pilot A, plus:

| Document | Store? | Remind expiry? | Master field? |
|---|---|---|---|
| Passport copy | Required | Yes | Optional number field |
| Residence permit / stamp evidence (Art. 18) | Required | Yes | residence_article + expiry |
| Work permit copy | Required (Art. 80) | Yes | number + expiry on doc or fields |
| Medical fitness (first issue) | Optional checklist | Optional | Document only |
| Health insurance certificate | Optional checklist | Optional | Document only |
| Police clearance / blood type / lease | **Not** HR master | — | Outside / transient GP folder only |

---

## 6. Confirmed software P0s (post-research)

Ordered for a **safe first Kuwait private-sector pilot** (prefer Pilot A, then B):

1. **Minimal `legal_entities` master** + default entity per company (employer-supplied CR/licence/PAM file text).  
2. **Hire-time immutable snapshot** from accepted offer (fields in §2).  
3. **Employee category + nationality + Civil ID number/expiry** with sensitive RBAC/audit.  
4. **Kuwait terminology fix:** residence permit (not iqama); Article 18 for private expats.  
5. **Art. 80 document set** wired in onboarding/compliance: contract, Civil ID, (+ work permit & residence if Pilot B) with expiry reminders.  
6. **Arabic contract path runbook** (upload governing AR PDF; EN translation optional).  
7. **Explicit outside-platform boundary** in product copy: PAM/MOI/PACI/PIFSS actions not performed by Wathefni.  
8. **Leave/OT/EOS remain non-enforcing** (store & request only) until counsel signs rate tables and eligibility.

**Deferred from audit “must before first client” if Pilot A:** residency/work-permit dual-write (still required before Pilot B).

---

## 7. Counsel questions (block enforcement, not pilot scaffolding)

1. Confirm current Arabic Art. 70: first-year annual-leave eligibility (**6 vs 9 months**) and whether weekends/holidays are excluded from the 30 days after Law 85/2017 (or successor).  
2. Confirm Art. 69 sick-leave wage bands currently applied by PAM/courts.  
3. Confirm Art. 51 EOS formulas after Law 17/2018 for **Kuwaiti** employees (PIFSS interaction) vs **expatriates**.  
4. Confirm which contract lodging channel is “competent authority” today (PAM e-contract vs labour office) for the client’s sector.  
5. Confirm whether soft validation of probation ≤100 **working** days is acceptable product behavior.  
6. Confirm OT premium matrix (+25% / weekly rest / holiday) and written-order evidence standard for the client’s operations.  
7. Confirm Civil ID / biometric data processing lawful basis and retention period for HR SaaS storage.  
8. Confirm current PACI late-registration fee and residency overstay fine schedule before any UI mentions amounts.  
9. Confirm whether GCC nationals in private sector follow Kuwaiti PIFSS rules or another regime for this client.  
10. Confirm exit-permit / 2025 travel rules (if any) before any offboarding checklist claims.

---

## 8. Recommended implementation sequence

**Still no implementation in this phase — sequence for a future remediation project only.**

| Step | Scope | Depends on |
|---|---|---|
| 0 | Choose Pilot A (nationals) or B (mixed); counsel answers Q1–Q4, Q7 | Owner |
| 1 | Legal-entity minimal schema + Setup Console fields (text identifiers) | Step 0 |
| 2 | Hire snapshot from accepted offer → employee | Step 1 |
| 3 | Employee category, nationality, Civil ID sensitive fields + permissions | Step 2 |
| 4 | Rename residency types; Art. 18 enum; remove iqama canonical naming | Step 3 |
| 5 | Art. 80 document matrix for chosen pilot; expiry reminders; dual-write for Pilot B | Step 4 |
| 6 | Arabic governing-contract upload runbook + UI copy (outside PAM/MOI) | Step 5 |
| 7 | Isolated synthetic qualification; then first real client | Steps 1–6 |
| 8 | Only after counsel: optional inert→reviewed leave/OT tables (`legal_reviewed`) | Counsel |
| 9 | Country-pack registry packaging (P1) | After pilot evidence |
| — | EOS calculator, PIFSS remittance, PAM/MOI APIs, SA packs | **Out of sequence** |

---

## 9. Final research statement

Evidence supports a **narrow, Art. 80-centred Kuwait private-sector pilot**: employing legal entity, hire snapshot, Civil ID + nationality, Arabic contract retention, and (for expats) Article 18 residence + work-permit copies with reminders — while **keeping PAM/MOI/PACI/PIFSS transactions outside Wathefni** and **refusing enforced leave/OT/EOS rules** until Kuwait counsel signs current texts and amendments.

Several prior “country-pack” ambitions (iqama naming, universal GP document masters, automatic fines, immediate EOS math, full pack registry) are **not supported as first-pilot necessities**.

**Stop.** No implementation.
