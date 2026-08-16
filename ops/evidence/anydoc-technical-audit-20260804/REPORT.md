# AnyDoc Technical Audit & Benchmark (non-production)

**Stamp:** `20260804`  
**Scope:** Research only. No production document route changed. No deploy.

**Verdict: CONDITIONAL GO** for an isolated **office-format** shadow/canary adapter.  
**Not** a replacement for PDF hybrid authority or Mistral OCR / identity routes.

---

## 1. Official-source research summary

| Item | Finding |
|---|---|
| Repo | https://github.com/firecrawl/anydoc |
| License | **MIT** (Sideguide Technologies Inc., 2026) |
| Version audited | crate `0.1.3` / PyPI `firecrawl-anydoc==0.1.2` (same day as announce) |
| Language | Pure Rust; Node (`@firecrawl/anydoc`) + Python bindings |
| Output | Shared document model → GitHub-Flavored Markdown |
| PDF path | Delegates to **`pdf-inspector`** (AnyDoc pins **`0.1.7`**) |
| Hosted cousin | Firecrawl `/parse` adds OCR for scans — **out of scope** for local AnyDoc |
| Maintenance | Brand-new public release (2026-08-04); fuzz targets + robustness suite present |
| Relationship to pdf-inspector | AnyDoc **wraps** pdf-inspector for PDF only; other formats are native AnyDoc parsers |

**Architecture (from upstream README / `src/`):**

```
bytes → format detection (content markers)
     → format parser (doc/docx/ppt/pptx/xls/xlsx/odf/rtf/epub/csv)
     → Document model → GFM serializer
PDF  → pdf-inspector.process_pdf_mem → Markdown (bypass model)
```

**Hard resource limits** (`src/package/limits.rs`, non-configurable):  
128 MiB/entry, 512 MiB total archive, 100k entries, XML depth 256, 2M XML nodes, expansion caps, 128 MiB assets. Abuse fixtures in-repo all reject.

---

## 2. Supported-format matrix (exact)

| Format | Extensions (upstream) | Local audit |
|---|---|---|
| Word | `.doc` `.docx` `.docm` | DOCX OK; real `.doc` OK on official fixtures; stubs fail closed |
| PowerPoint | `.ppt` `.pps` `.pot` `.pptx` `.pptm` `.ppsx` `.ppsm` | PPTX OK; official `.ppt` OK |
| Excel | `.xls` `.xlsx` `.xlsm` `.xlsb` | XLSX OK; official `.xls` OK |
| OpenDocument | `.odt` `.ods` `.odp` | OK |
| RTF | `.rtf` | OK |
| EPUB | `.epub` | Official fixtures OK |
| CSV | `.csv` | OK (needs extension/explicit format) |
| PDF | `.pdf` | Text OK; scanned/image-only → **OCR required error** |

---

## 3. Wathefni context (why this matters)

Current foundation already has:

- **PDF:** `pdf-inspector==0.2.6` hybrid + Poppler fallback + Mistral OCR (when enabled)
- **DOCX:** `cv_docx` local XML
- **Spreadsheets:** never OCR
- **Identity:** Mistral Document AI only (frozen)
- **No GPT** document fallback

Gap: consistent local Markdown for **legacy Office + ODF + RTF + PPT/XLS** before any OCR decision. AnyDoc targets that gap. For PDF, Wathefni already owns a **newer** pdf-inspector than AnyDoc bundles.

---

## 4. Benchmark results (sandbox)

Harness: `ops/evidence/anydoc-technical-audit-20260804/adapter/anydoc_audit_bench.py`  
Package: isolated `.venv` (not production orchestrator).

### Generated + prior-eval corpus (29 files)

| Metric | Value |
|---|---|
| AnyDoc OK / fail | **21 / 8** |
| Median OK latency | **~0.32 ms** |
| p95 OK | **~7.5 ms** |
| Max OK | **~25 ms** (large labor-law PDF) |
| Deterministic re-hash | **21/21** OK runs identical |
| Peak RSS (approx) | **~43 MB** process |

Failures were expected: scanned/image PDFs, intentional stubs, malformed zip/PDF.

### Official AnyDoc fixtures (61 files)

| Cohort | Result |
|---|---|
| Good fixtures | **43/43 OK**, median **~0.25 ms** |
| Malformed | 6/10 still produce something (recovery policy); rest error |
| Abuse (zipbomb, deepxml, hugerepeat, …) | **8/8 rejected** — no unexpected OK |

### PDF vs existing Wathefni pin (`pdf-inspector 0.2.6`)

| File | AnyDoc | pdf-inspector 0.2.6 |
|---|---|---|
| text PDF | OK (same char count) | OK |
| mixed prior-eval | OK + OCR pages flagged internally | OK + `pages_needing_ocr=[2]` |
| scanned / image-only | Fail: OCR required | Fail / empty + OCR pages |
| Kuwait labor PDF | OK, **3321 Arabic chars** | comparable native path |

**Conclusion:** For PDF, AnyDoc does not beat Wathefni’s hybrid; it re-wraps an **older** inspector. Keep PDF on current hybrid + Mistral.

### Office / structure spot checks

- DOCX: headings, bullets, tables (merged cells present; header row slightly noisy)
- XLSX: markdown tables; merged “Totals” row retained as a cell
- PPTX: title + bullets; **speaker notes** as blockquote
- CSV/ODT/ODS/ODP: clean tables/headings
- Arabic DOCX/CSV/XLSX/PPTX/ODT + bilingual PDF: Arabic codepoints preserved

---

## 5. Comparison vs current production paths

| Dimension | AnyDoc | Current Wathefni |
|---|---|---|
| Text PDF completeness | Equal (inspector) | **Better authority** (0.2.6 + quality gates + Poppler veto) |
| Scanned PDF | Errors (correct) | Mistral OCR when enabled |
| Arabic PDF | Good on native text | Hybrid already measures mojibake/Arabic corruption |
| DOCX | Strong GFM | Existing `cv_docx` — AnyDoc may be **equal/better** structure |
| DOC/PPT/PPTX/XLS/XLSX/ODF/RTF/CSV | **Better** (unified) | Partial / ad hoc / not Markdown-unified |
| Tables / lists / notes | Strong | Varies by format |
| Latency | Sub‑ms–tens of ms | Poppler/OCR much slower when invoked |
| Security limits | Hard caps + fuzz | Must still quarantine upstream |
| Identity docs | **Must not use** | Mistral identity authority frozen |

---

## 6. Risks & required controls

1. **Version skew:** AnyDoc PDF → inspector **0.1.7** vs Wathefni **0.2.6** — do not route PDF through AnyDoc.
2. **Very new crate** (day-0 public) — pin version; shadow before authority.
3. **Not document intelligence** — no classification/identity extraction.
4. **Zip/OLE bombs** — rely on AnyDoc limits **and** existing intake size/malware gates.
5. **Partial recovery on malformed Office** — treat low-confidence Markdown like today’s soft-fail gates.
6. **Tenant isolation** — local bytes only; never send to Firecrawl `/parse` in this design.
7. **Preserve** originals, `content_sha256`, audit, envelope, workflow authority.

---

## 7. Recommended routing & fallback contract

```
Supported structured office (docx/doc/pptx/ppt/xlsx/xls/odt/ods/odp/rtf/csv[/epub])
  → AnyDoc local parse (shadow/canary)
  → quality/confidence checks (chars/words/alpha/Arabic corruption/empty)
  → canonical Markdown representation
  → existing classification / CV V2 / validation / workflows

PDF (all)
  → existing local hybrid (pdf-inspector 0.2.6) → Poppler veto → Mistral OCR as today
  → DO NOT dual-run AnyDoc PDF in authority path (duplicate older inspector)

Scanned / image-only / mixed low-confidence / AnyDoc fail
  → existing Mistral OCR route (CV/images) or soft-fail if OCR disabled

Identity / civil ID / passport / residency / work permit / medical
  → unchanged Mistral identity authority (never AnyDoc)

Spreadsheets used as data imports
  → prefer structured sheet parsers where already authoritative; AnyDoc Markdown is optional assist only
```

**Product rules preserved:** no GPT fallback; no auto-admit from parse quality; HR confirmation unchanged.

---

## 8. Better / equal / worse matrix

| Area | Rating |
|---|---|
| DOC / PPT / PPTX / XLS / XLSX / ODT / ODS / ODP / RTF / CSV → Markdown | **Better** than current fragmented paths |
| DOCX → Markdown | **Equal → slightly better** structure consistency |
| Text PDF | **Equal / slightly worse authority** (older inspector pin) |
| Scanned / mixed PDF needing OCR | **Worse alone** (by design) — must fall back |
| Identity documents | **Worse / forbidden** |
| Latency (local structured) | **Better** |
| Security abuse rejection | **Equal/good** (hard limits) |

---

## 9. GO / CONDITIONAL GO / NO-GO

### **CONDITIONAL GO**

Proceed only if:

1. Canary is **office formats only** (exclude PDF + identity).
2. Runs as **shadow/observation** or staging canary — not production authority yet.
3. Pins `firecrawl-anydoc` version; records engine/version in extraction provenance.
4. Fail-open to current readers on error/low confidence.
5. Quality gates mirror foundation (`empty`, mojibake, Arabic corruption, min chars).
6. No Firecrawl hosted `/parse` in the canary (local only).

**NO-GO** for: replacing hybrid PDF, replacing Mistral OCR, touching identity authority, or day-0 production authority without shadow evidence.

---

## 10. Smallest isolated canary adapter (proposal only — not deployed)

Suggested module (new file, unused by default):

`wathefni-orchestrator/anydoc_office_shadow.py`

- Input: bytes + filename/ext + `document_class`
- Allowlist: `doc,docx,ppt,pptx,xls,xlsx,odt,ods,odp,rtf,csv`
- Deny: `pdf`, images, identity classes
- Call `anydoc.to_markdown_bytes`
- Emit observation dict: `{engine, version, ms, chars, sha256, ok, error}` next to existing extract metadata
- `influences_routing=false` until a later qualify wave
- Flag: `WATHEFNI_ANYDOC_OFFICE_SHADOW=off|staging_shadow|production_shadow`

Do **not** wire into `extract_cv_document` authority in this audit.

---

## Evidence paths

- Research clone: `ops/evidence/anydoc-technical-audit-20260804/research/anydoc/`
- Corpus + harness: `corpus/`, `adapter/anydoc_audit_bench.py`
- Results: `results/benchmark.json`, `official_fixtures.json`, `arabic_evidence.json`, `pdf_compare.json`
