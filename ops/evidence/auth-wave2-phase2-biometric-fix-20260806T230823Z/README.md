# Phase 2 Face ID gating fix

## Finding
After PIN create, opt-in was skipped when `getBiometricAvailability().usable` was false (over-strict `BIOMETRIC_STRONG` gate and/or silent availability failures). With no preference stored, reopen correctly showed PIN only — never Face ID.

## Fix
- Usable = hardware + enrolled (not STRONG-only)
- Log availability for canary diagnosis
- One-time offer recovery on boot/lock if PIN exists and offer never shown
- Master flag: explicit `0` off; unset inherits PIN master on
- Settings enable/disable unchanged

## OTA
Group `aec3862c-70b5-47d3-9a2e-d7f07eade52b` · PIN=1 · BIOMETRIC=1

## Owner check
Force-quit → reopen (pull OTA) → expect **Use Face ID?** once → Enable → Face ID on later reopen.
Or Settings → Face ID toggle if already past PIN.
