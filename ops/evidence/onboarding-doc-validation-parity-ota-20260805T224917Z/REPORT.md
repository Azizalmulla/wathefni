# Document Validation Parity — Mobile Correction UX OTA

**Stamp:** `20260805T224917Z`  
**Update group:** `b6bccf66-d7a2-4b95-b5dd-73543f9faa86`  
**Runtime:** `0.1.0`  
**Channel / branch:** `canary`  
**Platforms:** iOS + Android  

| Platform | Update ID |
|---|---|
| iOS | `019fd41e-4220-751f-b5d5-72f427cc48c5` |
| Android | `019fd41e-4220-7c6b-a5b3-d745948dbb39` |

## Scope

- Clear EN/AR mismatch correction alerts (`document_validation_*`)
- Clear blurry/uncertain success advisory (`uploadNeedsReview`) when soft-gate allows with HR review
- No raw `422` / machine codes in user copy
- Wave 2A preview / version history / resubmit preserved
- Backend soft-gate remain Aziz + Talal allowlist only

## Smokes

| Check | Result |
|---|---|
| Mobile typecheck | PASS |
| EAS canary publish | PASS — group current on `canary` / `0.1.0` |
| UX calm-message rules | PASS |
| Soft allowlist live | Aziz `WATHEFNI-96599338566` · Talal `WATHEFNI-96550252254` |
| Prod doc-validation unit smoke | `OK onboarding doc validation parity local smoke` (after hybrid assist defensive fix) |

## Rollback

```bash
cd apps/wathefni-employee-mobile
npx eas-cli update:rollback b6bccf66-d7a2-4b95-b5dd-73543f9faa86 \
  --message "Rollback Document Validation Parity mobile UX 20260805T224917Z" \
  --platform all --non-interactive
```

(Republishes prior canary group / embedded as applicable.)
