# Onboarding Document Validation Parity — Soft-gate Canary

**Stamp:** `20260805T142303Z`  
**Scope:** Employee `/app/onboarding/documents` classify → verify → quality/identity/expiry gates. Wave 2A lifecycle unchanged. No bank ESS. No Authentication Wave 2. No GPT.  
**Canary:** Aziz `WATHEFNI-96599338566` · Talal `WATHEFNI-96550252254`  
**Mode:** **SOFT** (hard off)

## Behavior

| Outcome | Soft-gate | Hard-gate (not enabled) |
|---|---|---|
| Clear mismatch (wrong type, instruction screenshot, identity mismatch, expired, ID-as-photo, tiny/unreadable) | **Block** before store · correction message EN/AR · HTTP 422 | Block |
| Uncertain (low confidence / needs_review / name unverified / missing Civil ID side) | **Allow** → `submitted`→`processing` · HR-review flags in lifecycle meta + extraction | Block |
| Pass | Allow · normal Wave 2A submit | Allow |

### Shared stack (no new OCR authority)

- Classify/verify: existing `verify_onboarding_media_item` / `classify_onboarding_media_upload` (Kuwait/GCC + Mistral identity delegate)
- Identity/name: `validate_onboarding_document_identity` + `document_name_match`
- Routes: `document_processing_foundation.resolve_route` (PDF/image/Office)
- Hybrid PDF assist when hybrid engine configured (contracts/certs PDFs) — fail-open
- AnyDoc assist for Office extensions when authority/shadow available — fail-open
- `gpt_used` forced false

### Flags (prod drop-in)

```
WATHEFNI_ONBOARDING_DOC_VALIDATION_SOFT=on
WATHEFNI_ONBOARDING_DOC_VALIDATION_HARD=off
WATHEFNI_ONBOARDING_DOC_VALIDATION_COMPANIES=WATHEFNI
WATHEFNI_ONBOARDING_DOC_VALIDATION_EMPLOYEE_ALLOWLIST=WATHEFNI-96599338566,WATHEFNI-96550252254
```

Path: `/etc/systemd/system/wathefni-orchestrator.service.d/zzzz-onboarding-doc-validation-soft.conf`

## Qualification

| Check | Result |
|---|---|
| Local unit smoke (Civil ID / passport / contract / cert / photo) | `OK onboarding doc validation parity local smoke` |
| Prod unit smoke (same) | Pass |
| Wave 2A lifecycle regression | `OK wave2a local smoke` on prod |
| Health | active |
| Soft on / Hard off for allowlist | Confirmed in process environ |
| Governed versions / HR approval | Unchanged (append-only; HR final) |

Hard-gate stays **off** until live canary uploads show low false-rejection.

## Mobile

- `approvedErrorMessage` surfaces server `document_validation_*` correction copy
- Alert title “Please try again” / Arabic equivalent on validation blocks
- JS-only — ship via OTA / next internal build for device UX; API gate is live now

## Rollback

```bash
/opt/wathefni/backups/production-pre-onboarding-doc-validation-20260805T142303Z/ROLLBACK.sh
```

Removes soft-gate drop-in and restores prior orchestrator files.

## Owner live review

Ready for one review covering:

1. Aziz/Talal: upload correct Civil ID / passport / contract / photo → accept into processing  
2. Clear wrong file (e.g. passport bytes as Civil ID, or ID as personal photo) → blocked with clear message  
3. Blurry/uncertain file → still submits; HR sees review-needed  
4. Confirm Wave 2A checklist groups unchanged  

Do **not** enable `WATHEFNI_ONBOARDING_DOC_VALIDATION_HARD` until soak evidence.
