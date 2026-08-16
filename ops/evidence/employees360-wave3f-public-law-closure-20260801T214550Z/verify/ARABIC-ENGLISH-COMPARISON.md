# Arabic ↔ English comparison notes (Wave 3F)

**Method:** Official Arabic PDF (`KuwaitLaborLaw-e.gov.kw.pdf` / MOJ byte-identical SHA256 `20eac588…d326`) rendered to PNGs (`arabic-page-*.png`). Automated `pdftotext` remains font-garbled and was **not** used as authority. English reading uses Official Gazette Issue 963 extract archived from the CAWTAR clearinghouse PDF (watermarked; **secondary reading aid**, cites Issue 963 — 21 Feb 2010).

| Article | Arabic page | Arabic verification | English verification | Comparison |
|---|---|---|---|---|
| 2–5 (scope / exclusions) | `arabic-page-02.png` | **PASS** — private sector; marine/oil residual; exclude other-law workers + domestic | **PASS** — Gazette extract Arts. 2–5 | Match |
| 6 (minimum rights floor) | `arabic-page-02.png` | **PASS** | **PASS** | Match — law is floor |
| 28–31 (contract form / fixed term) | `arabic-page-07.png` | **PASS** — written Arabic contract; fixed term 1–5 years; auto-renew | **PASS** | Match |
| 32 (probation) | `arabic-page-07.png` | **PASS** — ≤100 working days; terminate without notice; employer still pays EOSB for period; once per employer | **PASS** | Match |
| 41 (summary dismissal a/b) | `arabic-page-09.png` | **PASS** — (a) no notice/comp/benefit; (b) keep EOSB; appeal + arbitrary-dismissal damages; Ministry notify | **PASS** | Match |
| 42 (abandonment) | `arabic-page-09.png` | **PASS** — 7 consecutive / 20 separate days → deemed resignation; Art. 53 EOSB | **PASS** | Match |
| 44 (unlimited notice) | `arabic-page-09.png` + `arabic-page-10.png` | **PASS** — 3 months monthly / 1 month other; pay-in-lieu; job-search day/8h; garden leave (exempt, still paid/service) | **PASS** | Match |
| 47 (fixed-term damages) | `arabic-page-10.png` | **PASS** — wrongful early end → damages ≤ remaining-term remuneration | **PASS** | Match |
| 48–50 (worker exit / death / employer status) | `arabic-page-10.png` | **PASS** | **PASS** | Match |
| 51–53 (EOSB) | `arabic-page-11.png` | **PASS** — formulas present (10/15 non-monthly; 15/month monthly; resignation fractions) | **PASS** | Match on 2010 text. **Law 17/2018 amendment not in base PDF** — Payroll owns formulas + amendments |
| 54 (service certificate) | `arabic-page-11.png` | **PASS** — duration, position, last remuneration; no harmful expressions; return documents | **PASS** | Match |
| 73 (leave cash on end) | `arabic-page-15.png` | **PASS** — cash for accumulated annual leave on contract end | **PASS** | Match |
| 80 (personnel file) | `arabic-page-16.png` | **PASS** — permit, contract, civil ID, leaves, OT, accidents, penalties, EOS date/reasons, return receipts | **PASS** | Match |
| 144 (one-year lawsuit horizon) | `arabic-page-25.png` | **PASS** — worker suits not heard after one year from contract end | **PASS** | Match |

**OCR note:** `pdftotext-utf8.txt` and empty `arabic-article-excerpts-utf8.txt` demonstrate failed automated extraction. Visual PNG verification is the Arabic authority path for this pack.
