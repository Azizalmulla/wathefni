# Auth Wave 2 Phase 4 — Forgot PIN confirm copy

**Stamp:** `20260807T042705Z`  
**OTA:** `1f0fcfdb-0d27-4d21-97e6-d657bc7a589b` (canary, runtime `0.1.0`)

## Change

Forgot PIN shows confirmation before any clear:

- Title: Reset your PIN?
- Body: You'll need to sign in again with a new activation code, then create a new PIN.
- Buttons: Cancel · Continue

Clear of PIN, Face ID preference, and local session happens only after **Continue**. Recovery path unchanged.

## Prove

- Phase 4 unit: 29/29 (`prove/unit.txt`)
- EN/AR keys + Cancel/Continue wiring checked
