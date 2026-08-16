# Bank ESS P2 — production employee workflow (WATHEFNI canary)

**Verdict:** **PASS**  
**Stamp:** `20260807T083709Z`  
**P1 OCR:** frozen / proven (real Gulf Bank letter)  
**Auth Wave 2 Phase 6:** not started  

## Production loop shipped

Upload bank certificate → extract (P1 path) → employee confirms/corrects → submit **proposed** → HR review → payroll approve → **Apply** → payroll-effective.

## What changed in P2

### Employee (mobile)
- Document-first remains primary (upload certificate)
- Differentiated EN/AR notes: confirm, partial, uncertain, unreadable, wrong document, missing IBAN, correction hint
- Correction/resubmit is document-first (upload or edit with non-masked prefill)
- Never prefills `*` masked values into inputs

### HR (dashboard)
- Evidence shows masked **extracted** fields under the certificate
- Marks fields the employee corrected before submit
- Status flags: uncertain / wrong document / missing IBAN / manual entry

### Backend
- `CONTRACT_VERSION=bank_ess_v1_p2_production_workflow`
- Sanitize flags: `wrong_document_type`, `missing_iban`
- Evidence re-link after withdraw/reject (same `evidence_ids` on resubmit)
- **P1 frozen:** MIME sniff + HR extraction always masked

## Prove (real certificate `1786090542147.pdf`)

| Gate | Result |
|---|---|
| P2 unit | **4/4 PASS** |
| P2 live | **19/19 PASS** |
| Rich extract (Gulf Bank / KW IBAN) | PASS |
| Confirm/correct → pending_hr | PASS |
| Duplicate submit blocked / idempotent replay | PASS |
| Invalid KW IBAN rejected | PASS |
| Effective unchanged until Apply | PASS |
| HR current vs proposed vs extracted (masked) | PASS |
| Apply writes effective | PASS |
| Aziz FP unchanged | `0f349ce848ab5e4b` PASS |
| AR next_step | PASS |
| Dashboard needles | PASS |
| Mobile OTA canary | `a61e1f11-469e-41b7-9bb9-2078c682e82b` |

## Residuals / gaps

1. Physical device soak of new failure-copy strings (EN/AR RTL) after OTA pull — API-proven, UI not screenshot-proven.
2. Wrong-document / missing-IBAN paths proven via sanitize unit flags; live matrix used the good real certificate for the happy path (invalid IBAN + duplicate covered live).
3. Fixture PDF is sensitive; keep under stamp `fixture/` only.

## Paths

- Local: `ops/evidence/bank-ess-p2-production-workflow-20260807T083709Z/`
- Remote: `/opt/wathefni/production-evidence/bank-ess-p2/20260807T083709Z/`
- Backup: `/opt/wathefni/backups/production-pre-bank-ess-p2-20260807T083709Z/`

## Rollback

Restore `employee_bank_ess.py`, `app.py`, `kuwait_gcc_document_intelligence/extraction.py` from backup; restore prior dashboard www; republish prior canary OTA (`95d11ede-…` P1); `systemctl restart wathefni-orchestrator`.
