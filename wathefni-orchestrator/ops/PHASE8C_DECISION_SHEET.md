# Phase 8C — Decision sheet (human approvals required)

**Status:** awaiting your yes/no decisions  
**Date:** 2026-07-12  
**No canary execution authorized by this sheet**

Sensitive employee identifiers are stored only in the private ops evidence path and in the operator chat response — not below.

Private record (VPS, chmod 700):  
`/opt/wathefni/evidence/phase8c-canary-private/employee-candidates-private.json`  
`/opt/wathefni/evidence/phase8c-canary-private/decision-sheet-private.md`

---

## 1. Recommended canary employee (public fields only)

| Field | Value |
|---|---|
| Primary fingerprint | `2c08123fca34` |
| Why | Internal IT role; unique phone; zero invite/session; no cross-company conflict |
| Blocker | `employment_status` currently null → needs canonical `active` via R1B after approval |
| Alternates | `fbd61fad4485`, `f95cc3108abe` (same status blocker) |

Eligible now: **0**. Eligible after active-status only: **3**.

---

## 2. Recommended owner assignments

| Role | Recommended primary | Recommended backup |
|---|---|---|
| HR/data owner | Aziz Almulla | Hamad Almulla |
| Employee-support owner | Hamad Almulla | Aziz Almulla |
| Technical-rollback owner | Fouad (workspace owner `f.***@disruptv.tech`) | Aziz Almulla |
| Privacy-request owner | Support owner (unless you name another) | — |

If the canary employee is also the rollback owner, record overlap and keep Aziz as backup for the first four hours.

---

## 3. Recommended privacy mailbox

**`privacy@wathefni.ai`** — role-based; 2 business-day response target; must be created/routed and monitored before invite.

---

## 4. Privacy wording requiring approval

- Live URL: `https://wathefni.ai/employee-app/privacy`
- Notice: `INTERNAL-CANARY-NOTICE-v1`
- Scope: internal one-employee canary; `hr_task_only`; `personal_photo` only
- Retention recommend: 90-day ops metadata; photo HR decision within 30 days after close; accept B2 ~46-day backup persistence

---

## 5. Exact yes/no approvals required

1. Approve primary candidate fingerprint `2c08123fca34` (or name an alternate fingerprint) — yes / no  
2. Authorize `employment_status=active` via R1B for the approved candidate before invite — yes / no  
3. Approve owner set (Aziz HR, Hamad support, Fouad rollback) — yes / no  
4. Provide activation window — ______  
5. Approve mailbox `privacy@wathefni.ai` and confirm monitoring — yes / no  
6. Approve privacy page + notice wording — yes / no  
7. Approve retention values above — yes / no  
8. Approve onboarding item `personal_photo` only — yes / no  
9. Confirm you will obtain employee consent/ack before final GO — yes / no  
10. Do **not** issue execution GO until the completed checklist is returned

---

## Technical pause

Flags/modules unchanged and OFF. No invite, onboarding row, employee mutation, or canary execution performed by this readiness pass.
