# Kuwait docs qualification matrix — live HTTP production

**Stamp:** `20260806T033827Z`  
**Mode:** minted canary employee session → live uvicorn `127.0.0.1:8010` (no in-process TestClient)  
**Runner:** `wathefni-orchestrator/ops-smoke-kuwait-docs-qual-matrix.py`  
**Employee:** Aziz canary `WATHEFNI-96599338566` · disposable items only  
**Bank ESS:** out of scope

## Invariants

| Check | Result |
|---|---|
| Real `civil_id` SHA | `fe98f7d9d481578804a3ca3e19ca96ad4b4fa6e046f46e25d4ab21d9e15f0bb7` unchanged (accepted) |
| Canary leftovers after cleanup | 0 checklist / 0 compliance / 0 governed versions |
| Isolation | per-type subprocess · `REQ_TIMEOUT=120s` · `TYPE_TIMEOUT=360s` · retries=1 · partials on disk |
| Fixtures | synthetic PACI/canary PNGs under `fixtures/` — never Aziz real accepted docs |

## Matrix verdicts

All six types: **partially proven**. No type **missing/broken** after work_permit + employment_contract fixture rerun.

Shared partial (all types): `hr_ocr_summary_ui_hidden` — OCR fields are stored and returned on journey/API, but HR UI still surfaces only dates / review_status / rejection_reason / versions.

| Type | Verdict | Proven highlights | Partial | Missing |
|---|---|---|---|---|
| Civil ID F+B (`civil_id_dual_side_canary`) | partially proven | linkage, wrong-doc reject, F+B upload, OCR stored, expiry, versions, HR receive, preview, approve, reject→replacement, cross-employee blocked | identity_matching, hr_ocr_summary_ui_hidden | — |
| Passport | partially proven | full path incl. identity_matching + cross-type reject + HR round-trip | hr_ocr_summary_ui_hidden | — |
| Residence | partially proven | full path; identity N/A by design | hr_ocr_summary_ui_hidden | — |
| Work permit | partially proven | full path after expiry fixture fix (`2028-01-31`) | hr_ocr_summary_ui_hidden | — |
| Employment contract | partially proven | full path after textured fixture (glare FP on flat white) | hr_ocr_summary_ui_hidden | — |
| Personal photo | partially proven | upload + HR round-trip; sparse OCR expected | hr_ocr_summary_ui_hidden | — |

First-pass fixture failures (preserved, then fixed via isolated rerun):

- `docs_qual_work_permit` → HTTP 422 `expired_document` (fixture expiry 2026-01-31)
- `docs_qual_employment_contract` → HTTP 422 `glare_or_shadow` (flat-white synthetic)

## HR projection / approve / reject / replace

For every applicable type:

1. Employee upload → version `pending_hr_review`
2. HR journey hit on same `item_id` / canary `document_type`
3. Preview HTTP 200
4. Approve → employee status `accepted`
5. Reject → `replacement_required` → replacement upload path exercised
6. Cross-employee upload blocked (`404 item_not_found` for Talal)

## Exact extracted-field schemas (stored)

### Civil ID dual-side (pair OCR proposal)

Top-level keys: `authoritative`, `document_number`, `expiry_date`, `hr_review_recommended`, `hr_warnings`, `issue_date`, `pair_validated_at`, `parts`, `parts_schema`

Proven sample values: `document_number=290000001234`, `expiry_date=2030-01-14`  
Parts schema `civil_id_v1` with `front`/`back` slots (`present`, `file_id`, `detected_side`, `hr_warning`, …). Pair gate OK on F+B.

### Passport

`document_type`, `side`, `full_name`, `full_name_ar`, `full_name_en`, `name`, `document_number`, `nationality`, `date_of_birth`, `issue_date`, `expiry_date`, `confidence`, `extraction_status`, `authoritative`

### Residence

`document_type`, `side`, `full_name`, `full_name_ar`, `full_name_en`, `name`, `document_number`, `nationality`, `issue_date`, `expiry_date`, `employer_or_sponsor`, `confidence`, `extraction_status`, `authoritative`

### Work permit

`document_type`, `side`, `full_name`, `full_name_en`, `name`, `document_number`, `issue_date`, `expiry_date`, `employer_or_sponsor`, `confidence`, `extraction_status`, `authoritative`

### Employment contract

`document_type`, `full_name`, `name`, `employer_or_sponsor`, `confidence`, `extraction_status`, `authoritative`

### Personal photo

`authoritative`, `confidence`, `extraction_status` (no identity/expiry fields — expected)

## Fields stored but not shown to HR UI

HR UI shows: `expiry_date`, `issue_date`, `review_status`, `rejection_reason`, `versions`.

API/journey OCR present but **not** rendered in HR summary UI:

| Type | Hidden from HR UI (API present) |
|---|---|
| Civil ID | `document_number` (+ pair `parts` / warnings not summarized in UI) |
| Passport | `full_name`, `full_name_en`, `full_name_ar`, `name`, `document_number`, `nationality`, `date_of_birth`, `side`, `confidence` |
| Residence | `full_name`, `full_name_en`, `full_name_ar`, `name`, `document_number`, `nationality`, `side`, `employer_or_sponsor`, `confidence` |
| Work permit | `full_name`, `full_name_en`, `name`, `document_number`, `side`, `employer_or_sponsor`, `confidence` |
| Employment contract | `full_name`, `name`, `employer_or_sponsor`, `confidence` |
| Personal photo | `confidence` |

## Pipeline fixes confirmed during this wave (canary / shared)

1. Disposable canaries dual-write `compliance_documents` on **isolated** canary `document_type` (never alias into real `civil_id` / `passport`).
2. Nested `db_connect` around approve/reject removed (deadlock on `FOR UPDATE`).
3. Richer `ocr_proposal` persisted on employee receipt.
4. DocVal canary aliases for `docs_qual_*` validation targets.
5. Dual-side side-gate / legacy `missing_side` interaction (prior stamp) held under live F+B.

## Cleanup / regression

- Canary checklist + compliance + governed versions wiped → remaining **0**
- Real Civil ID snapshot after cleanup: accepted + expected SHA
- `smoke-test-onboarding-civil-id-dual-side.py` → **OK** (force smoke allowlist; prod Aziz allowlist must not be left as the smoke key)
- Live uvicorn `/docs` + `/openapi.json` → HTTP 200

## Artifacts

- `MATRIX.json` — consolidated verdicts + schemas
- `partials/` — per-type JSON + orchestrator/rerun logs + smoke + civil snapshot
- `fixtures/` — synthetic PNGs used for the run

## Not claimed

- Mobile onboarding **not** complete until Bank ESS qualification
- HR OCR summary UI still partial (API-complete, UI-hidden)
- Civil ID canary identity_matching remained partial on this run
