# Phase 2 — Face ID opt-in must not OTP

## Root cause
Boot recovery offered Face ID with `sealedSessionRef` set but `me` unset.
`finishBiometricOptIn` did `if (!me) setStatus('signedOut')` → activation screen,
discarding the in-progress local session path without classifier wipe (tokens may still
have been in SecureStore, but UX forced OTP).

## Fix
- Remove `!me → signedOut` from opt-in
- `resumeAfterBiometricOptIn` unseals via existing session / SecureStore
- Soft `/me` failures re-seal to PIN; wipe only via hardened classifier
- OTA `3d4d10ca-1852-473b-b912-a32de97d5245`

## Restore
Aziz phone `99338566` · code **295905**
