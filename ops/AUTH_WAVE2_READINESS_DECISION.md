# Auth Wave 2 — readiness decision

**Date:** 2026-08-07 (Phase 5 closed; invitation/delivery is a separate stream)  
**Decision:** Phase 5 **fully proven** — do **not** start Phase 6  
**Frozen contract:** `ops/AUTH_WAVE1_FROZEN_CONTRACT.md`  
**Phase 5 contract:** `ops/AUTH_WAVE2_PHASE5_DEVICE_SECURITY_CONTRACT.md`  
**Invitation/delivery (separate):** `ops/EMPLOYEE_APP_INVITATION_DELIVERY_CONTRACT.md` · evidence `ops/evidence/employee-app-invitation-delivery-20260807T061923Z/`  
**Evidence (Phase 5):** `ops/evidence/auth-wave2-phase5-access-reset-copy-20260807T053517Z/` (and `auth-wave2-phase5-device-security-20260807T045603Z/`)  
**Current OTA:** `7f1731ad-d482-4b7a-a2fc-502fa1a987c8`

## Verdict

One-device-at-a-time preserved. HR revoke kills sessions. Employee sees calm **access reset** copy only for definitive revoke (`app_access_revoked`), not for temporary network/server failures.

Invitation/delivery to the employee (email/WhatsApp, no SMS, no normal HR code handoff) is canary-proven separately and does **not** reopen Auth Wave 2 or start Phase 6.

## Auth Wave 2 — phase boundaries

| Phase | Scope | Status |
|---|---|---|
| **0 — Wave 1 freeze** | Document + regress | **done** |
| **1 — Local PIN + session hardening** | PIN gate | **done** |
| **2 — Biometrics** | Face ID / Touch ID cold start | **partial** |
| **3 — Idle / background lock** | Overlay timeout PIN | **proven** |
| **3B — Overlay Face ID** | Gate + nav preserve | **under review** |
| **4 — Simple PIN recovery** | Forgot PIN + 5-fail | **partial — physical pending** |
| **5 — Basic device security** | Current device · sign-out · HR revoke · new-device notice · access-reset copy | **fully proven** |
| **6+** | deferred — do not start |

## Explicit non-actions

- Do **not** begin Phase 6.
- Do **not** add multi-device trust, device naming, or remote wipe.
- Activation **delivery** channels are owned by the invitation/delivery contract (not Phase 6).
