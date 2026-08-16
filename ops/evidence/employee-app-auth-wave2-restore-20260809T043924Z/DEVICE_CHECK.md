# Device check — Auth Wave 2 restore

1. Force-quit Employee App · reopen · pull canary OTA `f226bdf5-d48e-49ef-b172-7c3672a0723e`.
2. Sign in as **Aziz** (or any eligible Employee App user).
3. Confirm:
   - PIN create/unlock returns after OTP if no PIN yet
   - Face ID / biometric opt-in after PIN when hardware allows
   - Background ≥ auto-lock timeout → unlock overlay (Face ID → PIN fallback)
   - Settings shows Change PIN / biometric toggle when capable
4. Optional: Noura / other allowlisted Employee App users should also get PIN (no longer Aziz/Talal-only).
