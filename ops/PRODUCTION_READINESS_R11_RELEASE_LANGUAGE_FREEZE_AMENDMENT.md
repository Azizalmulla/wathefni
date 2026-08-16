# Production Readiness R11 — Release Language Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R11_RELEASE_LANGUAGE_FULL_PASS`
**Date:** 2026-08-16

## What freezes with R11

1. Employee, HR co-bundle, and standalone HR Mobile catalogs must keep EN/AR key parity for the critical store/canary surfaces listed in the full pass.
2. `I18nManager.forceRTL` wiring stays in both employee and HR co-bundle i18n entrypoints.
3. Arabic OS permission strings remain in `locales/ar.json`.
4. HR Web leave/payroll/talent/auth keep bilingual branches. **The HR Web UX redesign is not authorised by this freeze.**
5. Physical RTL (PH-11) is not claimed.

Continue physical qualification, clean canary, and the store build gate.
