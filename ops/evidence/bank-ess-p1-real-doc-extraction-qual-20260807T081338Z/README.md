# Bank ESS P1 — real-document extraction qualification (WATHEFNI canary)

**Verdict:** **PASS**  
**Stamp:** `20260807T081338Z`  
**Fixture:** `fixture/1786090542147.pdf` (Gulf Bank IBAN letter, 1-page PDF)  
**P2:** not started  
**Auth Wave 2 Phase 6:** not started  

## What was proven

| Check | Result |
|---|---|
| Bank name extraction | **PASS** — Gulf Bank |
| Account holder extraction | **PASS** |
| Kuwait IBAN extraction + validation | **PASS** — `KW35…9548` (30 chars, kw_iban ok) |
| Account number when present | **PASS** — `****9548` |
| Optional branch / SWIFT / currency | **PASS** branch `Al Fanar Mall`, SWIFT `GULBKWKW` · currency SKIP (not on letter) |
| Extraction confidence / warnings | **PASS** — confidence ~0.98–1.0, status `extracted`, warnings `[]` |
| Employee confirm/correct → proposed submit | **PASS** — `pending_hr` |
| Original evidence private | **PASS** — owner 200, other 403/404, no `storage_ref` |
| Extracted values non-authoritative | **PASS** — `authoritative: false`; no verified row for request |
| HR current vs proposed + evidence + extraction | **PASS** — status/confidence; IBAN masked in extraction |
| Payroll-effective unchanged until Apply | **PASS** — seed FP unchanged; Aziz `0f349ce848ab5e4b` unchanged |

## Fixes required during this qual (shipped to canary)

1. **MIME sniff for extensionless bank-evidence paths** — storage refs have no `.pdf` suffix; Mistral was getting `data:application/octet-stream…` and returning HTTP 400. Fixed in `kuwait_gcc_document_intelligence/extraction.py` (`_sniff_mime` + pass-through `mime_type`).
2. **HR extraction masking** — evidence `extraction.proposed` now always masks IBAN/account number on review surfaces (audited reveal remains separate). `employee_bank_ess.list_evidence`.

## Architecture (unchanged)

Upload → private evidence → shared Kuwait/GCC Mistral `bank_certificate` → non-authoritative proposed → employee confirm → HR verify → Apply effective.

## Residuals

- Currency not present on this letter (SKIP, not FAIL).
- Physical mobile confirm/correct UI soak still optional (API path proven).
- Fixture file retained under `fixture/`; treat as sensitive — do not publish broadly.

## Paths

- Local: `ops/evidence/bank-ess-p1-real-doc-extraction-qual-20260807T081338Z/`
- Remote: `/opt/wathefni/production-evidence/bank-ess-p1-realdoc/20260807T081338Z/`
