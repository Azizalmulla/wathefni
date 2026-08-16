# Bank ESS P1 — document-first Kuwait bank certificate (WATHEFNI canary)

**Verdict:** **PASS**  
**Stamp:** `20260807T080230Z`  
**P2:** not started  
**Auth Wave 2 Phase 6:** not started  

## Authority model (unchanged)

| Layer | Written by |
|---|---|
| Proposed | Employee confirm/correct → sealed submit |
| Verified | **HR approval only** |
| Payroll-effective | **Payroll Apply only** |

OCR / extraction is **non-authoritative**. It never writes `employee_bank_verified` or `employee_bank_effective`.

## Architecture used

```
PDF/image bank letter
  → POST /app/bank/evidence (private storage)
  → shared_channel_extraction(document_type=bank_certificate)
       via kuwait_gcc_document_intelligence (Mistral Document AI)
  → extraction_json on employee_bank_evidence (authoritative=false)
  → mobile confirm/correct → seal proposed → pending_hr
  → HR BankReviewPanel: current vs proposed + evidence + extraction summary
  → HR approve = verified; Apply = effective
```

No separate bank-only OCR stack. Reuses Kuwait/GCC shared intake + structuring schemas.

## Extraction schema

`wathefni_kw_bank_certificate_v1` / `bank_certificate_json_schema()`:

- `document_type`, `country_code`
- `bank_name`, `account_holder`, `iban`, `account_number`
- `branch`, `swift`, `currency` (optional)
- `overall_confidence`, `field_confidence`, `warnings`, `unreadable_reason`

Sanitized employee/HR projection: `employee_bank_ess.sanitize_bank_extraction` →
`proposed`, `status`, `confidence`, `uncertain`, `needs_manual_fallback`, `authoritative: false`.

## Storage / model changes

Additive columns on `employee_bank_evidence` (idempotent `ensure_bank_ess_schema`):

- `extraction_json jsonb` (raw + `sanitized` + `bank_ess_layer=proposed_only`)
- `extraction_status text`
- `extraction_confidence double precision`

`CONTRACT_VERSION = bank_ess_v1_p1_document_first`  
Flag: `WATHEFNI_BANK_ESS_OCR_V1=on` · `WATHEFNI_BANK_ESS_OCR_V1_COMPANIES=WATHEFNI`  
(drop-in `bank-ess-ocr-p1.conf`)

## Evidence path

Upload → private storage ref → authorized GET only (`/app/bank/evidence/{id}` /
dashboard HR path). On submit, `evidence_ids` link rows to the request.
Replace/reattach during correction/resubmission supported.

## What shipped

### Backend
- `kuwait_gcc_document_intelligence` — `bank_certificate` type + materializer
- `employee_bank_ess.py` — OCR helpers, evidence extraction persistence, list projection
- `app.py` — `/app/bank/evidence` returns extraction + `proposed_fields` + fail-open manual fallback

### Mobile
- Document-first primary path (upload certificate → confirm/correct)
- Manual fallback + replace certificate
- EN + AR copy; payroll-effective stays visible while change pending
- Canary OTA group `95d11ede-9516-4d85-bc73-936167b83fa3`

### Dashboard
- `BankReviewPanel` — concise extraction status/confidence/warnings (not raw OCR)
- Dist: `PostHire-DYgMUWG9.js`

## Prove

| Check | Result |
|---|---|
| P1 focused unit | **8/8 PASS** |
| P1 focused live | **12/12 PASS** |
| Qual matrix Bank ESS | **51/51 PASS** (incl. P1 extraction cases) |
| Qual matrix onboarding | **31/31 PASS** |
| OCR never writes verified/effective | PASS |
| Invalid KW IBAN rejected | PASS |
| HR verify ≠ effective; Apply writes effective | PASS |
| Evidence link + isolation | PASS |
| EN/AR status | PASS |
| Dashboard Extraction needles | PASS |
| Aziz effective FP unchanged | `0f349ce848ab5e4b` PASS |
| Mobile OTA canary | **PASS** `95d11ede-9516-4d85-bc73-936167b83fa3` |

## Residuals

1. **Live “good certificate → rich field extraction”** was not proven against a real bank letter image/PDF on canary; synthetic PDF/PNG correctly fail-opened to `needs_review` / manual fallback. Unit sanitize covers the good-extraction projection. Physical Aziz/Talal walk with a real IBAN letter still useful.
2. Physical EN/AR + mobile/desktop UI soak on canary devices (OTA pulled) — not automated here.
3. P2 not started. Auth Wave 2 Phase 6 not started.

## Paths

- Local: `ops/evidence/bank-ess-p1-document-first-20260807T080230Z/`
- Remote: `/opt/wathefni/production-evidence/bank-ess-p1/20260807T080230Z/`
- Backup: `/opt/wathefni/backups/production-pre-bank-ess-p1-20260807T080230Z/`

## Rollback

Restore backed-up `employee_bank_ess.py`, `app.py`, `kuwait_gcc_document_intelligence/{schemas,intake,extraction}.py` from the backup path; remove `/etc/systemd/system/wathefni-orchestrator.service.d/bank-ess-ocr-p1.conf` (or set OCR off); restore prior dashboard www; republish prior canary OTA (`d73cd3c7-…` P0) if needed; `systemctl daemon-reload && systemctl restart wathefni-orchestrator`. Extraction columns are additive and safe to leave.
