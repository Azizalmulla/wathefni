# Employee Onboarding — Document Validation Parity

**Stamp:** `20260805T142303Z` (soft-gate canary)  
**Module:** `wathefni-orchestrator/onboarding_doc_validation_parity.py`  
**Hook:** `POST /app/onboarding/documents` (before store)  
**Prerequisite:** Wave 2A lifecycle (`ops/EMPLOYEE_ONBOARDING_WAVE2A_LIFECYCLE.md`) — **unchanged**

## Goal

Bring employee-app uploads to WhatsApp-parity classify/verify quality without GPT, preserving governed versions and HR final approval.

## Soft vs hard

| | Soft (live canary) | Hard (future) |
|---|---|---|
| Clear mismatches | Block + correction message | Block |
| Uncertain | Allow → processing + HR flags | Block |
| Allowlist | Aziz + Talal | Same until GO |

Promote hard only after false-rejection evidence is low.

## Item coverage (qualified in unit smoke)

- Civil ID — type match, name match, side advisory, expiry  
- Passport — type/name/expiry  
- Employment contract — verify + uncertain→HR  
- Education certificate — verify + hard-mode needs_review  
- Personal photo — storage-only; blocks ID-looking uploads  

## Flags

See evidence REPORT. Hard default **off**.

## Out of scope

Bank ESS · Authentication Wave 2 · Dashboard hard-gate · Auto-reject historical weak OCR
