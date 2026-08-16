# Authentication Wave 2 — Audit & Plan (no implementation)

**Status:** **AUDIT / PLAN ONLY** — do not change authentication code until owner approval  
**Date:** 2026-08-06  
**Stamp:** paired with onboarding close `20260806T004945Z`  
**Scope:** Employee mobile app + `/app/auth/*` orchestrator  
**Out of scope:** HR dashboard / HR mobile password auth · onboarding DocVal · bank ESS implementation

---

## 1. Current authentication architecture

### Model
HR-provisioned **activation OTP** only. No employee password. Opaque **access + refresh** bearer tokens (not JWT); server stores **SHA-256 hashes** only (`employee_sessions`).

### Employee mobile
| Piece | Path | Live? |
|---|---|---|
| Activate UI (phone + 6-digit code) | `app/(auth)/activate.tsx`, `ActivationView.tsx` | Yes |
| Session authority | `src/auth/AuthProvider.tsx` | Yes |
| SecureStore tokens | `src/auth/session.ts` (`WHEN_UNLOCKED`) | Yes |
| Password / biometrics / local PIN | — | **No** |

### Orchestrator routes (`app.py`)
| Route | Behavior |
|---|---|
| `POST /app/auth/request-code` | Re-issue if prior invite · generic OK · cooldown |
| `POST /app/auth/activate` | Redeem invite → session · Kuwait 8↔965 aliases |
| `POST /app/auth/refresh` | Rotate access+refresh hashes in place |
| `POST /app/auth/logout` | Revoke presented access token |
| `GET /app/me` | Profile + capabilities from session |

### TTLs / limits (server)
Invite 24h · code 6 digits · max 5 attempts · access **7d** · refresh **180d** · resend cooldown 60s.

### Gates (fail-closed)
`WATHEFNI_EMPLOYEE_APP` · company module · lifecycle/employment active · **`WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST`** (Aziz/Talal canary).

### Delivery
`deliver_app_activation_code` via outbound ladder (often WhatsApp) — not a dedicated SMS OTP product.

### Contrast
Dashboard / HR mobile: email + password. Do not reuse `/app/auth/*` for operators (`ADMIN_MOBILE_SCOPE_FREEZE`).

---

## 2. Security and UX gaps

| Gap | Why it matters |
|---|---|
| No biometric / local PIN unlock | Every reopen relies on long-lived SecureStore session |
| No idle / app-lock | Session usable whenever OS unlocks Keychain |
| No auth-level device binding | New device = re-activate (revokes siblings) but no labeled devices |
| Recovery UX incomplete | `request-code` only if previously invited; else HR re-invite |
| Channel = outbound ladder | WhatsApp/session delivery ≠ SMS OTP expectations |
| No step-up for sensitive ESS | Bank/ESS uses `session_epoch` kill switch, not client re-auth |
| Still allowlist canary | Not open Kuwait workforce login |

---

## 3. Proposed production login / session flow

1. **First device:** HR creates invite → code delivered → employee enters phone + code → opaque session in SecureStore.  
2. **Returning day (Wave 2 target):** local biometric or PIN unlocks existing tokens; server refresh as today.  
3. **New device:** new/re-issued invite or `request-code` → activate **revokes** prior sessions (`reactivated_via_invite`).  
4. **Logout / offboard / ESS epoch:** server revoke · client clears SecureStore + cache.  
5. **Sensitive actions (later):** optional local step-up; keep ESS `session_epoch` as hard server kill switch.

Identity for all `/app/*` continues to come **only** from the session (never client-supplied `employee_key`).

---

## 4. Biometrics and PIN behavior (proposed)

| Rule | Detail |
|---|---|
| Role | **Local unlock only** — never a server credential |
| Storage | Wrap / gate access to SecureStore tokens; do not replace refresh |
| Factors | Face ID / Touch ID preferred; PIN fallback; EN+AR |
| Failed biometrics | Fall back to PIN; after N PIN fails → force re-OTP activate |
| Lost PIN / new install | No local recovery of tokens → activation OTP again |
| Accessibility | WHEN_UNLOCKED already; evaluate AFTER_FIRST_UNLOCK carefully |

**Must not:** treat biometrics as proof to the API, or mint sessions without activate/refresh.

---

## 5. OTP, recovery, and new-device flow (proposed)

| Scenario | Behavior |
|---|---|
| First activation | Unchanged: HR invite + outbound code |
| Re-request code | Keep silent generic OK; cooldown; prior-invite required |
| New phone | Activate with new/re-issued code → revoke old sessions + push |
| Never invited | No self-registration; HR must invite |
| Recovery copy | Clear EN/AR: “Ask HR for a new code” vs “Request a new code” |
| SMS product | Optional later ops track — not required to start Wave 2 local unlock |

---

## 6. Session rotation, revocation, logout (keep + extend)

### Already live — freeze as Wave 1 contract
- Opaque hashed tokens; refresh rotates both secrets  
- Logout revokes presented token  
- Offboarding / `revoke_employee_app_access`  
- ESS `session_epoch` invalidates stamped sessions  
- Activate is single-use; re-activate revokes siblings  
- Refresh re-checks company module / lifecycle gates  

### Wave 2 additions (plan)
| Addition | Notes |
|---|---|
| Idle / background lock | Local only; re-prompt biometric/PIN |
| Optional session list | Device label + revoke-other (server) |
| Step-up | Re-unlock before bank submit when Wave 2B ships |
| Logout-all from settings | Calls existing revoke APIs |

---

## 7. Implementation phases and risks

| Phase | Scope | Risk |
|---|---|---|
| **0 — Freeze Wave 1 auth contract** | Document activate / request / refresh / logout + revoke-on-new-device | Drift vs old Phase7E `409 already_activated` docs |
| **1 — Local unlock** | PIN + biometrics gating SecureStore · no new server auth | Lost PIN UX; Keychain accessibility; EN+AR; canary-only first |
| **2 — Recovery polish** | Copy + HR re-invite vs request-code paths · optional session list | Channel reliability; enumeration safety |
| **3 — Optional device binding** | Fingerprint on activate/refresh | False locks on OS restore; multi-phone households |
| **4 — Idle + step-up** | Background lock; re-auth before bank/ESS | Over-prompt vs Kuwait norms; ESS epoch interaction |
| **5 — Controlled rollout** | Beyond Aziz/Talal under existing freezes | Owner change-control |

### Highest risks
1. Treating biometrics as **server** auth  
2. Breaking canary activate / Kuwait phone aliases  
3. Conflicting with ESS `session_epoch` / bank encryption freezes  
4. Shipping SMS OTP without delivery/ops readiness  

---

## 8. Evidence already proving Wave 1 (do not redo)

| Stamp | Proof |
|---|---|
| `20260805T015417Z` | activate / refresh / logout PASS |
| `20260805T033940Z` | Kuwait phone alias activate on prod edge |
| `20260805T021500Z` | Client logout clears SecureStore + cache |

---

## 9. Approval gate

**No authentication code, native deps (`expo-local-authentication`), or flag changes until this audit is approved.**  
After approval, start Phase 0 freeze note + Phase 1 local unlock on Aziz/Talal only.
