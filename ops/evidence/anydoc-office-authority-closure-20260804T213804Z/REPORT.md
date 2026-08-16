# AnyDoc Office Authority Closure Wave

**Stamp:** `20260804T213804Z`  
**Host:** `root@76.13.63.68`  
**Pin:** `firecrawl-anydoc==0.1.2`  
**Flags:** `WATHEFNI_ANYDOC_OFFICE_AUTHORITY=production` + `WATHEFNI_ANYDOC_OFFICE_SHADOW=production_shadow`  
**Health:** production `:8010` OK  

**Final freeze status: FROZEN** — AnyDoc Office integration closed under format-correct authority models. No further AnyDoc work in this track.

---

## Format-by-format authority decision

| Format | Decision | Model |
|---|---|---|
| **DOCX** | **PRODUCTION AUTHORITY** | Primary local normalization when quality gates pass; `cv_docx` immediate fallback |
| **PPTX** | **PRODUCTION AUTHORITY** | Document-text normalization only; promote when existing text weak/empty |
| **ODT** | **PRODUCTION AUTHORITY** | Document-text normalization (gov-style ODF included) |
| **ODS** | **PRODUCTION AUTHORITY** | Document-text normalization only (not payroll/import authority) |
| **XLSX** | **MD NORMALIZATION ONLY** | openpyxl / import parsers remain structured authority; AnyDoc MD attached for understanding |
| **CSV** | **MD NORMALIZATION ONLY** | Raw/text + DictReader remain authority; AnyDoc MD attached only |
| **RTF** | **SHADOW ONLY** | No promotion |
| **ODP** | **SHADOW ONLY** | No promotion |
| **DOC / XLS / PPT** | **SHADOW ONLY** | Legacy; fail-open on stubs |
| **PDF / images / identity** | **DENIED** | Never AnyDoc; no hosted `/parse` |
| **GPT** | **NONE** | No GPT fallback |

---

## Qualify counts (19 production-shaped files)

Corpus: CVs, offer/HR letters, decks, employee lists, payroll XLSX/CSV, government-style ODT/ODS, Arabic/bilingual priors, legacy shadow samples.

| Metric | Local / VPS staging |
|---|---|
| Promoted (DOCX/PPTX/ODT/ODS) | **12** |
| Fallback (legacy shadow-only reasons) | **2** |
| Material disagreement | **1** (RTF shadow baseline only) |
| Deterministic | **17 / 17** |
| Structured XLSX integrity | **PASS** |
| Structured CSV integrity | **PASS** |
| Identity denied | **PASS** |
| PDF denied | **PASS** |

### By extension (local)

| Ext | n | Promoted | MD-only | Shadow-only | Disagree |
|---|---|---|---|---|---|
| DOCX | 5 | 5 | 0 | 0 | 0 |
| PPTX | 3 | 3 | 0 | 0 | 0 |
| ODT | 2 | 2 | 0 | 0 | 0 |
| ODS | 2 | 2 | 0 | 0 | 0 |
| XLSX | 3 | 0 | 3 | 0 | 0 |
| CSV | 2 | 0 | 2 | 0 | 0 |
| RTF | 1 | 0 | 0 | 1 | 1 |
| DOC | 1 | 0 | 0 | 1 | 0 |

---

## Arabic / bilingual quality

| Sample | Arabic chars | Engine |
|---|---|---|
| `cv_ar_en.docx` | 84 | anydoc (promoted) |
| `contract_offer_ar_en.docx` | 85 | anydoc (promoted) |
| `deck_ar.pptx` | 52 | anydoc (promoted) |
| `gov_notice_ar.odt` | 83 | anydoc (promoted) |
| `gov_roster.ods` | 23 | anydoc (promoted) |
| `prior_roster_ar.xlsx` | 27 | existing_structured + MD attach |
| `payroll_aug2026.csv` | 15 | existing_structured + MD attach |

No Arabic-corruption / mojibake failures on authority-candidate promotions.

---

## Structured-data integrity (XLSX / CSV)

Proven for employee list + payroll fixtures:

- `text_unchanged=true` (extract path text not replaced by Markdown)
- `structured_rows_unchanged=true` (openpyxl / DictReader row tuples identical before/after)
- `influences_payroll=false`, `influences_migration=false`
- `normalized_markdown_attached=true` for understanding only
- Live production: CSV role `markdown_normalization_only`; XLSX openpyxl rows intact (3)

Import / payroll / migration code paths that call openpyxl or `csv.DictReader` directly were not redirected through AnyDoc.

---

## Production stamp

| Item | Value |
|---|---|
| Stamp | `20260804T213804Z` |
| Module | `/opt/wathefni/orchestrator/anydoc_office_authority.py` |
| Drop-in | `zzz-anydoc-office-authority.conf` |
| Live DOCX | `selected_engine=anydoc`, `method=anydoc_docx`, promoted |
| Live CSV | structured unchanged |
| Evidence | `ops/evidence/anydoc-office-authority-closure-20260804T213804Z/` |
| Remote | `/opt/wathefni/evidence/anydoc-office-authority-closure/20260804T213804Z/` |

---

## Rollback

```bash
/opt/wathefni/backups/production-pre-anydoc-office-authority-20260804T213804Z/ROLLBACK.sh
```

Restores prior modules/drop-ins and restarts orchestrator. Staging backup: `/opt/wathefni/backups/staging-pre-anydoc-office-authority-20260804T213804Z/`.

---

## Contracts preserved

- Originals + SHA-256 + tenant `company_code` on provenance blobs  
- CV V2 / classification / validation / admission / workflow authority unchanged by design (`influences_*=false` on structured/admission/payroll/migration)  
- DOCX blocks preserved on promote  
- Automatic fallback to existing readers on quality fail / timeout / ConvertError  
- Local bytes only; pinned `0.1.2`

---

## Freeze

**AnyDoc Office track is frozen.** Resume post-hiring visual sequence (Shifts UX direction: control hierarchy, identity rail, tile density, overnight copy) as the next workstream.
