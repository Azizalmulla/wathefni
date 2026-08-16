# BrowserStack real-device foundation gate — stop-point verdict

**Stamp:** 2026-08-11  
**Rule:** API PASS ≠ MOBILE PASS  
**Broad HR+Employee release:** **NO-SHIP**

## What was proven

| Item | Result |
|---|---|
| RC chooser vs intended auth | **Reconciled.** IPA 0.3.0 (23) embeds principal chooser; canary OTA ships UnsignedEntry. |
| Canary OTA for intended UI | **Published** `c349bb2b-…` then follow-up auth-hardening OTA |
| OTA soak → UnsignedEntry on real iPhone | **MOBILE_PASS** (`00-launch-unsigned`) |
| Canonical E2E HR principal | **Created** `e2e-hr+mobile@wathefni.internal` owner on WATHEFNI (secrets in `~/.config/wathefni/e2e.env` only) |
| Disposable Leave fixtures | **Working** (`provision-leave-fixture.py` → approve + reject requested leaves for Talal) |
| Secure credential strategy | **In place** (`load_secrets.py`, fixture env, password redaction in SUMMARY) |
| HR API spine | **API_SPINE** (mobile auth login, me, priorities, leave list, assistant capabilities) |
| BrowserStack HR login | **FAIL** — see blockers |
| HR tabs / Leave Approve / Reject | **FAIL** (blocked on login) |
| Leave DB reconcile after UI | **N/A** (mutations never executed on device) |

## BrowserStack evidence

1. Build `f4c9eb771dd01934f11423082cab99e8d71777fa`  
   https://app-automate.browserstack.com/dashboard/v2/builds/f4c9eb771dd01934f11423082cab99e8d71777fa  
   iPhone 15 / 17.3 · unsigned **passed** · login failed (stayed on sign-in; keyboard up)

2. Build `bac778d7fc9c39db8690e21437054191b0efc176`  
   https://app-automate.browserstack.com/dashboard/v2/builds/bac778d7fc9c39db8690e21437054191b0efc176  
   unsigned **MOBILE_PASS** · login failed because Maestro typed  
   `e2e-hr+mobile@wathefnit.internal` (domain corrupted: **wathefnit**)

Local evidence dirs:
- `ops/evidence/mobile-e2e-gate-bs-20260811T061112Z`
- `ops/evidence/mobile-e2e-gate-bs-20260811T062531Z`

## Blockers / debt

1. **RELEASE BLOCKER — HR login on real device**  
   Maestro iOS `inputText` corrupted the work-email domain. Mitigations in flight: split local/domain input, `spellCheck={false}` / autofill off, hideKeyboard before Sign in.

2. **Face ID / biometric unlock** — `BLOCKED_NATIVE` / `PHYSICAL_DEBT` (suite taps Not now).

3. **Local simulator host** — still not ready (disk/JDK/runtime); BrowserStack is the real-device layer.

4. **Credential hygiene** — password briefly landed in BrowserStack `setEnvVariables` evidence; rotated; SUMMARY redaction fixed. Prefer BrowserStack secret injection long-term.

## Architecture now permanent

```
RC IPA + canary OTA
 → load_secrets (~/.config/wathefni/*.env)
 → provision-leave-fixture.py (disposable approve/reject IDs)
 → Maestro bs-smoke on BrowserStack
 → reconcile-leave-decision.py (operator_mobile channel)
 → SHIP / NO-SHIP
```

## Strict SHIP / NO-SHIP (foundation stop-point)

| Gate | Verdict |
|---|---|
| UnsignedEntry real-device | **MOBILE_PASS** (architecture proven) |
| HR login real-device | **NO-SHIP** |
| HR tabs | **NO-SHIP** |
| Leave Approve | **NO-SHIP** |
| Leave Reject | **NO-SHIP** |
| Broad release | **NO-SHIP** |

Do not expand the matrix until HR login + Leave Approve/Reject are genuine MOBILE_PASS with DB reconcile.
