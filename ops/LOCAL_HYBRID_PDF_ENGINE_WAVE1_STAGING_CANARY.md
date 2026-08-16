# Local Hybrid PDF Engine Wave 1 — CV Staging Alternate-Path Canary

Date: 2026-08-04  
Mode: **staging only**  
Evidence: `ops/evidence/local-hybrid-pdf-engine-wave1-20260803T230331Z/`  
Production routing / authoritative Poppler path: **unchanged**

## Verdict

| Scope | Result |
|---|---|
| Staging canary implemented + qualified | **PASS** |
| Hybrid authoritative? | **No** |
| Production deploy this wave | **No** |
| Rollback by unsetting flag | **Proven** |
| CV production **shadow** canary | **CONDITIONAL GO** (observation-only; owner approval required) |
| Hybrid as production authority | **NO-GO** |

## Flag

```text
WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=staging_canary   # default off
```

Rollback: remove staging drop-in `zzzz-local-hybrid-pdf-engine-wave1.conf`, `daemon-reload`, restart staging.

## What runs when enabled

For eligible CV PDFs on staging:

1. **Authoritative:** existing Poppler/Mistral extract → evidence → Ranking inputs → CV Extraction V2 (Document AI) → materialize current (unchanged)
2. **Alternate (non-authoritative):** local hybrid engine → `document_envelope@1` → same `run_v2_extraction` with hybrid merged text as `extracted_text` (Document AI still runs on PDF bytes; not bypassed)
3. Compare OCR pages, latency, Mistral cost, envelope provenance, and structured V2 fields
4. Hybrid never materializes current V2, never publishes profile facts, never replaces Ranking

Modules:

- `wathefni-orchestrator/local_hybrid_pdf_engine.py` (Wave 0)
- `wathefni-orchestrator/local_hybrid_pdf_engine_canary.py` (Wave 1)
- Hook in staging `app.py` CV worker (fail-open)
- Qualify: `ops/qualify-local-hybrid-pdf-engine-wave1-staging.sh`

## Fixture set (synthetic / anonymized only)

9 approved corpus PDFs: Arabic digital, bilingual, multi-column, scanned, mixed, broken-encoding, English digital.

No real candidate records created for qualify.

## Acceptance gates

| Gate | Result |
|---|---|
| Zero false OCR skips | **PASS** |
| Zero structured-field accuracy reduction | **PASS** |
| Zero missing Ranking evidence | **PASS** |
| V2 completion same or better | **PASS** |
| Envelope `document_envelope@1` | **PASS** |
| Flag-off skips canary | **PASS** |
| Rollback proven | **PASS** |

### Structured compare method

Dual back-to-back Document AI calls on the same PDF are non-deterministic (observed employment/skills count drift). Acceptance therefore uses:

**shared Document AI annotation + validate against Poppler text vs hybrid merged text**

Full dual Document AI outputs are still recorded as observation (`structured_dual_document_ai_observation`) for cost/path parity. Hybrid remains non-authoritative either way.

## OCR / cost / latency (qualify run)

| Metric | Value |
|---|---:|
| Hybrid OCR billable pages | 4 (~$0.016) |
| V2 Document AI auth (estimate) | ~$0.050 |
| V2 Document AI hybrid alternate (estimate) | ~$0.050 |
| False OCR skips | 0 |

Notable routing:

- Arabic Wave 0: Poppler OCR page, hybrid keeps usable native Arabic (not a false skip)
- Broken encoding: hybrid forces OCR (including Wave 0 fixture Poppler accepts)
- Scanned / mixed: page agreement with Poppler

## Production status

- Production hybrid flag: **absent**
- Production drop-in: **absent**
- Staging flag after qualify: **re-enabled** `staging_canary` for ongoing observation

## GO/NO-GO — tightly controlled CV production shadow canary

**CONDITIONAL GO**, only if owner approves all of:

1. Flag name remains distinct, e.g. `WATHEFNI_LOCAL_HYBRID_PDF_ENGINE=production_shadow` (not `staging_canary`)
2. Behavior = **shadow/compare only** — identical to staging: Poppler authoritative; hybrid never current V2 / Ranking / Candidate Knowledge
3. Cost caps + sample rate (Document AI runs twice when canary fires)
4. Monitor false-skip + acceptance gates on live CVs before any later influence wave
5. Instant rollback by unsetting flag

**NO-GO** for making hybrid authoritative or replacing Poppler in this wave.

## Not done

- No production deploy
- No authoritative cutover
- No Migration Wave 1-B
- No bypass of Document AI / V2 schema / evidence / Ranking / Candidate Knowledge
