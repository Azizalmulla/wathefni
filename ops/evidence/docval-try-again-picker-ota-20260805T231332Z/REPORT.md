# DocVal Try again → reopen picker (canary OTA)

**Stamp:** `20260805T231332Z`  
**Update group:** `18b27224-09d0-4fcf-b6da-cd91e28c21bf`  
**Runtime / channel:** `0.1.0` / `canary`

| Platform | Update ID |
|---|---|
| iOS | `019fd434-8846-742c-9f4d-066d8beb4359` |
| Android | `019fd434-8846-7f37-8412-88938a8dc1f6` |

## Fix

- Blocked upload Alert **Try again** reopens camera/library/files picker for a **new** selection.
- Card **Try again** does the same.
- Rejected file is **never** auto-resent; no “Retry same file” action.
- Calm EN/AR validation copy unchanged; no raw codes.
- Aziz canary item reset to `pending` + upload enabled.

## Smoke (owner)

1. Force-close / reopen Wathefni (pull canary OTA).  
2. Onboarding → **CANARY ONLY — Civil ID upload test**.  
3. Upload a clear mismatch → blocked calm message.  
4. Tap **Try again** → picker opens (not silent resend).  
5. Choose a different file.

## Rollback

```bash
cd apps/wathefni-employee-mobile
npx eas-cli update:rollback 18b27224-09d0-4fcf-b6da-cd91e28c21bf \
  --message "Rollback DocVal Try again picker 20260805T231332Z" \
  --platform all --non-interactive
```
