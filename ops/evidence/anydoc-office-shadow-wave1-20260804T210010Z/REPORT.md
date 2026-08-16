# AnyDoc Office Shadow Canary Wave 1

**Stamp:** `20260804T210010Z`  
**Host:** `root@76.13.63.68`  
**Scope:** DOC/DOCX, PPT/PPTX, XLS/XLSX, ODT/ODS/ODP, RTF, CSV  
**Excluded:** PDF, images, identity documents, hosted Firecrawl `/parse`  
**Authority:** unchanged — observation only (`influences_*=false`)

---

## Verdict

| Decision | Result |
|---|---|
| Wave 1 shadow (staging → production observation) | **GO — complete** |
| Office-format **authority** canary (next wave) | **CONDITIONAL GO** (narrow) |
| Production authority change in this wave | **NO — stopped** |

**CONDITIONAL GO** for a future authority canary limited to **DOCX + XLSX + CSV (+ ODT/ODS)** after a live `production_shadow` soak.  
**NO-GO** for immediate broad authority over RTF / PPT(X) / legacy DOC-PPT-XLS without longer soak and real Wathefni Markdown baselines.

---

## What shipped

| Item | Detail |
|---|---|
| Adapter | `wathefni-orchestrator/anydoc_office_shadow.py` |
| Pin | `firecrawl-anydoc==0.1.2` (shared prod venv) |
| Flag | `WATHEFNI_ANYDOC_OFFICE_SHADOW=off\|staging_shadow\|production_shadow` |
| Staging | drop-in `staging_shadow` on `wathefni-orchestrator-staging` |
| Production | drop-in `production_shadow` on `wathefni-orchestrator` (**observation only**) |
| Hook | `extract_candidate_cv_document` attaches metadata; never mutates text |
| Rollback | `/opt/wathefni/backups/production-pre-anydoc-office-shadow-20260804T210010Z/ROLLBACK.sh` |

Live prod proof (port **8010**):

- `WATHEFNI_ANYDOC_OFFICE_SHADOW=production_shadow`
- CSV extract: shadow blob present; `authority_text_unchanged=true`
- PDF denied; identity (`passport`/`civil_id`) denied
- `influences_routing=false`

---

## Staging results

### A) Local full corpus (33 allowlisted files)

Evidence: `results/local/staging_corpus_local_full33.json`

| Metric | Value |
|---|---|
| OK | **27 / 33** |
| Fail-open | **6** (malformed stubs / abuse fixtures) |
| Material disagreements | **4** |
| Informational (AnyDoc-only, no auth baseline) | **13** |
| Deterministic (re-hash match) | **27 / 27** |
| `influences_routing` always false | **true** |
| Pin | `0.1.2` |

Fail-open (expected): stub/abuse `.docx`/`.doc`/`.ppt`/`.xls` — ConvertError, production parser unchanged.

### B) VPS staging (17 generated bilingual fixtures)

Evidence: `results/staging_corpus_results.json`

| Metric | Value |
|---|---|
| OK | **14 / 17** |
| Fail-open | **3** (legacy stubs) |
| Material disagreements | **3** (2× RTF completeness vs raw RTF auth; 1× ODP quality gate) |
| Deterministic | **14 / 14** |
| PDF denied | `denied_extension_or_mime` |
| Identity denied | `identity_document_denied` |
| Smoke | **6/6 OK** |

---

## Format-by-format comparison

| Format | Shadow OK | vs Wathefni authority | Notes |
|---|---|---|---|
| **DOCX** | Yes (AR/EN) | Agree | Arabic CV preserved (62 Arabic chars); headings/lists present |
| **DOC** | Official fixtures OK locally; stubs fail-open | No auth baseline | Path/content-detect fallback (Python named format omits some aliases) |
| **PPTX** | Yes (AR/EN) | Informational (auth empty) | Slide text extracted; notes not separately asserted in this corpus |
| **PPT** | Official OK locally; stub fail-open | No auth baseline | Fail-open on garbage |
| **XLSX** | Yes (AR/EN) | Agree | Tables → Markdown; Arabic roster OK |
| **XLS** | Official OK locally; stub fail-open | No auth baseline | Bytes named `"xls"` fails → content/path fallback |
| **ODT/ODS** | Yes | Informational / agree | Arabic ODT OK |
| **ODP** | Parses | Short sample quality-gate fail | Treat as soak item before authority |
| **RTF** | Parses | Material disagreement | Auth harness reads raw RTF; AnyDoc emits short plain text — not an authority candidate yet |
| **CSV** | Yes (AR/EN) | Agree | Deterministic; live prod observation OK |
| **PDF** | Denied | N/A | Never routed |
| **Identity** | Denied | N/A | Never routed |

---

## Disagreement & fallback counts

| Bucket | Local 33 | VPS 17 |
|---|---|---|
| Fail-open (fallback to existing parser) | 6 | 3 |
| Material disagreement | 4 | 3 |
| Informational AnyDoc-only | 13 | 6 |
| Authority text mutated | **0** | **0** |

Material reasons (local): RTF `completeness_below_50pct` / `anydoc_quality_gate_failed`; ODP quality gate.  
Not counted as material: `anydoc_only_no_auth_baseline` (formats Wathefni does not Markdown-authority today).

---

## Arabic / bilingual evidence

| File | Arabic chars | Quality | Material disagreement |
|---|---|---|---|
| `cv_ar_en.docx` | 62 | OK | No |
| `deck_ar.pptx` | 32 | OK | Informational only |
| `roster_ar.xlsx` | 27 | OK | No |
| `table_ar.csv` | 35 | OK | No |
| `sample_ar.odt` | 23 | OK | Informational only |
| `memo_ar.rtf` | 13 | quality gate fail (short) | Yes (baseline artifact) |

No mojibake / Arabic-corruption flags on successful DOCX/XLSX/CSV/PPTX/ODT runs.

---

## Resource & security evidence

| Control | Status |
|---|---|
| Local bytes only | **true** (no network upload) |
| Hosted Firecrawl `/parse` | **false** / never called |
| Pin | `firecrawl-anydoc==0.1.2` installed in `/opt/wathefni/orchestrator/.venv` |
| Timeout floor/cap | 50ms–15s (prod drop-in **2000ms**) |
| Max bytes | 8 MiB default (shadow skip if larger) |
| Empty / mojibake / Arabic-corruption / min-char gates | Applied in `_quality_metrics` |
| Malware | `malware_gate=upstream_intake_required` — shadow does not bypass intake |
| Tenant | `company_code` recorded on blob; no cross-tenant I/O |
| Provenance | `content_sha256`, `output_sha256`, engine/version/latency/chars recorded |
| Original file | Unmodified; shadow reads bytes only |
| Workflow / CV V2 / admission / routing | Unchanged (`influences_*=false`) |

Abuse/stub fixtures fail closed at AnyDoc and fail-open for Wathefni — production path continues.

---

## Production shadow observation

| Check | Result |
|---|---|
| Flag live | `production_shadow` |
| Module present | `/opt/wathefni/orchestrator/anydoc_office_shadow.py` |
| Health | `200` on `127.0.0.1:8010` |
| Live CSV shadow | `ok`, latency ~5 ms, chars 99, output hash recorded |
| Authority unchanged | Proven (extract with flag on == flag off) |
| PDF / identity | Denied |

**Production authority was not changed.**

---

## GO / NO-GO for office-format authority canary

### GO (narrow, next wave — not this one)

Enable an **authority canary** only after soak, for:

1. **DOCX** (parity with `cv_docx`)
2. **XLSX / CSV** (structured tables)
3. Optionally **ODT / ODS** where Wathefni has no Markdown authority today

Gates before that wave:

- ≥7 days (or N≥ production office extracts) of `production_shadow` with fail-open rate and material disagreement rate within budget
- Explicit per-format promotion flag (not a blanket office switch)
- Still **never** PDF / images / identity / hosted `/parse`

### NO-GO (now)

- Broad office authority canary covering RTF + PPT(X) + legacy DOC/PPT/XLS in one shot
- Any change that lets AnyDoc influence classification, CV V2, validation, admission, or workflows
- Replacing PDF hybrid / Mistral identity paths

---

## Rollback

```bash
/opt/wathefni/backups/production-pre-anydoc-office-shadow-20260804T210010Z/ROLLBACK.sh
```

Removes prod drop-in, restores prior `app.py` / requirements, deletes new module if it did not exist pre-wave, restarts orchestrator.

Staging drop-in: `/etc/systemd/system/wathefni-orchestrator-staging.service.d/anydoc-office-shadow.conf`

---

## Evidence index

- Local: `ops/evidence/anydoc-office-shadow-wave1-20260804T210010Z/`
- Remote: `/opt/wathefni/evidence/anydoc-office-shadow-wave1/20260804T210010Z/`
- Qualify script: `ops/qualify-anydoc-office-shadow-wave1.sh`
- Smoke: `wathefni-orchestrator/smoke-test-anydoc-office-shadow-wave1.py`
- Prior audit: `ops/evidence/anydoc-technical-audit-20260804/REPORT.md`
