# NATLEX secondary index citations (Wave 3F)

Live fetch of ILO NATLEX returned HTTP 403 from this environment on 2026-08-01.
These records are retained as **secondary official indexing only** — not substitute Arabic texts.

| Record | URL | Role |
|---|---|---|
| Law No. 6/2010 (KWT-2010-L-83616) | https://natlex.ilo.org/dyn/natlex2/r/natlex/fe/details?p3_isn=83616 | Indexes private-sector Labour Law |
| Law No. 17/2018 (KWT-2018-L-108307) | https://natlex.ilo.org/dyn/natlex2/r/natlex/fe/details?p3_isn=108307 | Indexes Art. 51 amendment for Kuwaiti nationals / PIFSS interaction |

**Product implication:** Employees 360 does not encode EOSB formulas from NATLEX abstracts. Payroll owns all EOSB / social-security difference math. Full Official Gazette Arabic for Law 17/2018 was not retrieved this wave → EOSB remains **Payroll-only** with no E360 calculator.

**Authority hierarchy used:**
1. Official Arabic PDF (e.gov.kw / moj.gov.kw) — primary
2. Official Gazette Issue 963 English extract (archived reading aid citing Issue 963, 21 Feb 2010)
3. PAM homepage fetch (index only)
4. NATLEX metadata (secondary index; live 403)
