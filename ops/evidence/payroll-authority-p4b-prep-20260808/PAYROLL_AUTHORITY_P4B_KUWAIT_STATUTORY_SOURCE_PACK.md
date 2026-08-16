# Payroll Authority P4B Preparation — Kuwait Statutory Source Pack

**Pack ID:** `KW_STATUTORY_SOURCE_PACK_P4B_PREP_v1.0.0`  
**Date:** 20260808  
**Status:** research + candidate packaging only — **not activated**  
**Depends on:** P4A architecture (`ops/PAYROLL_AUTHORITY_P4A.md`) — frozen  
**Does not:** set `approved` / `legal_claim=true` / `counsel_signed=true` · unlock Mode A · remove SYNTHETIC_ONLY · enable PDF/payments

---

## Disclaimer

This pack is **software-ready counsel review material**, not legal advice and not Wathefni money authority.

- Arabic Official Gazette / PIFSS Arabic instruments prevail over English translations.
- English Labour Law text cited here is from commonly circulated private-sector Law No. 6/2010 translations (secondary for language; structure aligned to statute).
- Vendor blogs, EOR marketing, and AI summaries are **not** legal authority (used only to flag market practice conflicts).
- Every numeric rate remains **`legal_claim=false`** until a human legal/payroll reviewer signs P4B activation.

---

## Source hierarchy used

| Tier | Meaning | Examples in this pack |
|---|---|---|
| **P — Primary / official** | Statute, Official Gazette, PIFSS official site | Law No. 6/2010 Arts; Law No. 17/2018 (NATLEX/Gazette refs); PIFSS FAQ contribution table |
| **S — Secondary confirmation** | Reputable commentary / ILO index / consistent EN translations | kuwaitlaborlaw.com EN text; ILO NATLEX Law 17/2018 abstract; WageIndicator DecentWorkCheck |
| **X — Non-authority** | Vendor/blog/EOR — **not used as rates authority** | HLB, RemotePeople, Papaya, payrollmiddleeast.com |

Confidence: **H** high structure from primary · **M** medium (translation / operational nuance) · **UC** unresolved → **COUNSEL REVIEW REQUIRED**

---

## Master rule matrix

| Rule family | Proposed rule (candidate) | Applies to | Effective from | Primary source | Secondary confirmation | Confidence | Counsel status |
|---|---|---|---|---|---|---|---|
| **PIFSS — Basic** | EE 5% / ER 10% on basic insured salary ≤ **KD 1,500** | Kuwaiti insured (private/oil as applicable); wage elements per PIFSS FAQ | As published on PIFSS FAQ (confirm gazette effective dates) | PIFSS official FAQ contribution table | Consistent secondary summaries | **H** rates table · **M** wage-element mapping | **AWAITING_LEGAL_VALIDATION** |
| **PIFSS — Supplementary** | EE 5% / ER 10% on supplementary insured salary ≤ **KD 1,250** (excess over basic max) | Same | Same | PIFSS FAQ | Same | **H** rates · **M** base composition | **AWAITING_LEGAL_VALIDATION** |
| **PIFSS — Pension increase** | EE 2.5% / ER 1% on salary ≤ **KD 2,750** | Same | Same | PIFSS FAQ | Same | **H** | **AWAITING_LEGAL_VALIDATION** |
| **PIFSS — Financial remuneration** | EE 2.5% / ER none on ≤ **KD 1,500**; FAQ labels “(for 18 years of contribution)” | Insured meeting contribution-period conditions | Confirm | PIFSS FAQ | Secondary often folds into “+2.5%” without conditions | **UC** eligibility trigger | **COUNSEL REVIEW REQUIRED** |
| **PIFSS — Unemployment (private/oil)** | EE 0.5% / ER 0.5% on ≤ **KD 2,750**; FAQ: subject from **2013-05-01** private/oil | Private + oil sector insured | 2013-05-01 (PIFSS FAQ) | PIFSS FAQ | Same | **H** rates · **M** sector scope edge cases | **AWAITING_LEGAL_VALIDATION** |
| **PIFSS — remittance timing** | Contributions payable beginning of month following accrual month; delay >10 days → 1%/month additional | Employers | Ongoing | PIFSS FAQ | — | **H** | Remittance prep only (not payment rails) |
| **PIFSS — wage base private/oil** | Basic: salary + social + children + educational qualification allowance (manpower support) ≤1500; Supplementary: excess over basic max ≤1250 | Private/oil | Confirm | PIFSS FAQ (insured Q&A) | — | **M** | **COUNSEL REVIEW REQUIRED** on component mapping to Wathefni comps |
| **PIFSS — expatriate** | Not subject to Kuwait PIFSS employee/employer contributions | Expatriate employees | Ongoing | Practice + Social Security Law coverage design; PIFSS materials address Kuwaiti/GCC schemes | Widespread secondary | **M** (negative rule) | **COUNSEL REVIEW REQUIRED** to confirm no residual local schemes |
| **PIFSS — GCC national** | Extension of Insurance Protection — home-scheme contributions; **not** same as Kuwaiti PIFSS % table | GCC nationals working in KW | Extension law dates per PIFSS journey | PIFSS Extension of Protection / journey page | Secondary home-rate tables | **UC** exact % by home state | **COUNSEL REVIEW REQUIRED** — do not invent home rates |
| **OT ordinary** | +**25%** over original **remuneration** for overtime hours; written order; ≤2h/day; ≤180h/year; ≤3 days/week **or** ≤90 days/year | Private-sector workers under Law 6/2010 | Law 6/2010 in force (2010) | Law 6/2010 **Art. 66** | EN translation sites; WageIndicator | **H** premium · **M** simultaneous reading of weekly/annual caps | **AWAITING_LEGAL_VALIDATION** |
| **OT night premium** | Some secondary claim +50% night OT (19:00–06:00) | — | — | **Not found in Art. 66 EN text reviewed** | Papaya / vendor pages | **UC** | **COUNSEL REVIEW REQUIRED — do not encode** |
| **Rest-day work** | If called on weekly rest: original remuneration **+ ≥50%** **+** substitute day off; weekly rest ≥24 continuous hours after 6 working days | Private-sector | Law 6/2010 | **Art. 67** | EN translations; DecentWorkCheck | **H** structure | **AWAITING_LEGAL_VALIDATION** |
| **OT hourly divisor** | Art. 67 ¶2: rights calculated by dividing remuneration by **actual working days excluding weekends** (weekends still paid) | Impacts OT/rest/PH money math | Law 6/2010 | **Art. 67** | Arab Times / practice often cite **26** working days/month | **UC** exact divisor convention for 5-day weeks | **COUNSEL REVIEW REQUIRED** |
| **Public-holiday work** | Work on listed official holiday → **double remuneration** + additional day off | Private-sector | Law 6/2010 | **Art. 68** | EN translations | **H** | **AWAITING_LEGAL_VALIDATION** |
| **Public-holiday calendar** | Hijri NY, Isra/Mi’raj, Eid Al-Fitr (3), Arafat, Eid Al-Adha (3), Prophet’s Birthday, National Day, Gregorian NY | Private-sector paid holidays | Law 6/2010 | **Art. 68** list | Government calendars may add Liberation Day etc. | **M** — list in statute vs annual cabinet additions | **COUNSEL REVIEW REQUIRED** for complete annual calendar |
| **Sick leave bands** | Per year: 15d @100% · 10d @75% · 10d @50% · 10d @25% · 30d unpaid (75d total); medical report required | Private-sector | Law 6/2010 | **Art. 69** | Consistent secondary | **H** bands | **AWAITING_LEGAL_VALIDATION** |
| **Sick leave year basis** | “During the year” — calendar vs rolling employment year | — | — | Art. 69 wording | Secondary assume calendar year | **UC** | **COUNSEL REVIEW REQUIRED** |
| **Sick leave pay base** | “Pay” / “quarters of the pay” — basic vs full remuneration (Art. 55) | — | — | Art. 69 + Art. 55 | Secondary diverge | **UC** | **COUNSEL REVIEW REQUIRED** |
| **EOS monthly** | 15 days remuneration / year for first 5 years; **1 month** / year thereafter; **cap 1.5 years** remuneration; fractions pro-rata | Monthly-paid workers | Law 6/2010 | **Art. 51(b)** | Consistent secondary | **H** structure | **AWAITING_LEGAL_VALIDATION** |
| **EOS daily/hourly/piece** | 10 days / year first 5; 15 days thereafter; **cap 1 year** remuneration | Non-monthly paid | Law 6/2010 | **Art. 51(a)** | Same | **H** | **AWAITING_LEGAL_VALIDATION** |
| **EOS full entitlement events** | Full Art. 51 benefit if employer terminates; fixed term ends unreenewe; Arts 48–50; female resigns within 1 year of marriage | As Art. 52 | Law 6/2010 | **Art. 52** | Same | **H** | **AWAITING_LEGAL_VALIDATION** |
| **EOS resignation (indefinite)** | <3y: **none** (implied); 3–≤5y: **½**; 5–<10y: **⅔**; ≥10y: **full** | Worker terminates indefinite contract | Law 6/2010 | **Art. 53** | Same | **H** | **AWAITING_LEGAL_VALIDATION** |
| **EOS remuneration base** | Art. 62: entitlements on **last remuneration**; piecework averages; benefits averaged | All EOS | Law 6/2010 | **Art. 55, 62** | Secondary often wrongly use “basic only” | **M** | **COUNSEL REVIEW REQUIRED** — basic vs full remuneration |
| **EOS × PIFSS (Kuwaiti)** | Law **17/2018** amends Art. 51 interaction (full indemnity without SS offset per NATLEX abstract / Gazette 1391 6 May 2018). Pre-2018 text required net difference vs SS. Firm letters/debate on retroactivity & constitutionality. | Kuwaiti nationals on SS | 2018 (retroactivity disputed) | Law 17/2018 (Gazette) + Art. 51 history | NATLEX; Al-Jarida constitutional critique; Mashora pre-amendment offset memo | **UC** operational current rule + retroactive claims | **COUNSEL REVIEW REQUIRED** |

---

## Unresolved legal questions (must not be guessed)

1. **PIFSS “Financial remuneration” 2.5%** — exact trigger for “18 years of contribution”; private-sector applicability by hire date.  
2. **GCC nationals** — exact home-scheme % tables to store per nationality; never collapse into Kuwaiti PIFSS table.  
3. **Contributory wage mapping** — how Wathefni BASIC / allowances map to PIFSS basic vs supplementary elements.  
4. **OT night premium** — encode only if counsel finds primary support; Art. 66 EN text reviewed does not state 50% night OT.  
5. **Hourly divisor** — 26-day convention vs Art. 67 “actual working days excluding weekends” for 5-day employers.  
6. **Public holiday calendar** — Art. 68 list vs annually declared holidays (e.g. Liberation Day).  
7. **Sick leave year** — calendar year vs year of service; interaction with incurable-disease ministerial list.  
8. **Sick / OT / EOS pay base** — basic salary vs Art. 55 remuneration.  
9. **Law 17/2018** — current employer obligation for Kuwaiti EOS vs any remaining SS offset; treatment of periods before 2018.  
10. **Oil sector / special regimes** — Law 28/1969 petroleum labour interactions with Art. 66–69 / PIFSS.  
11. **Fixed-term resignation** — Art. 53 text addresses indefinite-term resignation; fixed-term early exit rules need counsel.  
12. **Remittance field schema** — official PIFSS portal form field map for D-class reporting (not payment processing).

---

## Candidate machine records

See:

- `ops/payroll_authority_p4b_candidate_records_v1.json` — machine-ready payload  
- `ops/seed-payroll-authority-p4b-candidates.py` — inserts **only** `awaiting_legal_validation` + `legal_claim=false` + `counsel_signed=false`
- `ops/PAYROLL_AUTHORITY_P4B_PREP.md` — prep index (not activation)

**Forbidden until human sign-off:** `approved`, `legal_claim=true`, `counsel_signed=true`, P3 legal money enablement, Mode A seal.

---

## Proposed counsel sign-off checklist (P4B activation gate)

- [ ] Arabic primary texts reviewed for Arts 51–53, 55, 62, 66–69  
- [ ] PIFSS contribution table + wage-element circulars confirmed current  
- [ ] GCC extension rates attached per nationality or explicitly unsupported  
- [ ] Law 17/2018 EOS/PIFSS interaction memo signed  
- [ ] Divisor / remuneration-base memo signed  
- [ ] Night OT decision: encode or permanently unsupported  
- [ ] Then flip candidates to `approved` + `legal_claim=true` + `counsel_signed=true` under P4B change control  
