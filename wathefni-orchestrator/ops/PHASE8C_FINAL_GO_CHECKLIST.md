# Phase 8C — Final GO checklist (post-decision update)

**Date:** 2026-07-12  
**Pilot company:** `WATHEFNI`  
**Canary employee fingerprint:** `2c08123fca34` (full key in private evidence only)  
**Execution status:** **NO-GO** — not final GO; canary not started

Private evidence (VPS, not git): `/opt/wathefni/evidence/phase8c-canary-private/`

---

## Gate status

| # | Gate | Status |
|---|---|---|
| G1 | Phase 8B production-dark green | **COMPLETE** |
| G2 | Pilot company `WATHEFNI` | **COMPLETE** |
| G3 | R1E fail-closed security cutover | **COMPLETE** |
| G4 | HR/data owner + backup named | **NAMED** — Aziz / Hamad; availability TBD |
| G5 | Support owner + backup named | **NAMED** — Hamad / Aziz; availability TBD |
| G6 | Rollback owner + backup with proven technical access | **INCOMPLETE** — Aziz/Hamad cannot execute fail-closed technical rollback today (see §Owners) |
| G7 | Exact one employee selected | **COMPLETE** — Fouad Burhamad approved |
| G8 | Active status + company + unique phone + zero invite/session | **COMPLETE** after authorized R1B |
| G9 | Employee consent + notice acknowledgment | **INCOMPLETE** — mandatory; not yet obtained |
| G10 | Privacy URL HTTP 200 | **COMPLETE** |
| G11 | Role mailbox active + monitored | **PARTIAL** — route accepts mail; human receive/monitor confirmation still required |
| G12 | Notice/privacy wording approved | **COMPLETE** in principle; live page matches approved content checks |
| G13 | Retention terms approved | **COMPLETE** (90 / 30 / ~46) |
| G14 | Provider inventory accepted for canary | **COMPLETE** (Hostinger, B2, Vercel; Octopus/Postmark unused for activation) |
| G15 | `personal_photo` only | **COMPLETE** |
| G16 | Activation window first-four-hours coverage | **INCOMPLETE** — TBD |
| G17 | Separate final execution GO | **NOT ISSUED** |

**Recommendation: NO-GO**

---

## Authorized R1B status transition (done)

| Field | Value |
|---|---|
| Employee fingerprint | `2c08123fca34` |
| Before | `employment_status=null` |
| After | `employment_status=active` |
| Durable `result_id` | `ce74a16d-b486-40df-b4bd-ff7a27ab5ecb` |
| Reason | `Approved internal Phase 8C employee-app canary eligibility` |
| Approval mode | `self_approved_internal_canary` |
| Operator | Fouad workspace owner (only normal operator with `employees.manage` + `employees.status.approve`) |
| Changed fields | `employment_status`, `updated_at` only |
| Idempotent replay | same `result_id` |
| Post-change verified | yes |
| Method | supported R1B API workflow — **no direct SQL** |

Private packet: `r1b-fouad-active-status.json`

---

## Owners — authority finding (blocks G6)

Approved names:

- HR/data: Aziz primary, Hamad backup  
- Support: Hamad primary, Aziz backup  
- Rollback: Aziz primary, Hamad backup  
- Fouad must **not** be rollback owner  

Production access check:

| Person | Normal dashboard operator? | Can execute technical rollback via fail-closed APIs? |
|---|---|---|
| Aziz Almulla | **No** (`legacy_hr_phone_bootstrap`) | **No** |
| Hamad Almulla | Yes (workspace) but **viewer** | **No** (no write/manage scopes) |
| Fouad (workspace owner) | Yes + employee grants | Yes — but **disallowed** as rollback owner |

**Required before marking owners complete:**

1. Convert Aziz to workspace authentication (normal operator), **or** name another non-canary workspace operator with production access as rollback primary.  
2. Grant that rollback operator the explicit scopes needed for module/flag rollback and employee administration.  
3. Confirm Aziz + Hamad availability for the activation window / first four hours.

---

## Privacy mailbox

| Check | Result |
|---|---|
| Address | `privacy@wathefni.ai` |
| MX | `inbound-smtp.us-east-1.amazonaws.com` |
| SMTP RCPT | **250 accepted** |
| Non-sensitive Postmark send | **accepted** (`MessageID` in private evidence) |
| Human receive confirmation | **Still required** |
| Named monitoring owner | Support primary **Hamad Almulla** (pending acknowledgment) |

---

## Privacy page version

Live `https://wathefni.ai/employee-app/privacy` → **HTTP 200**  
Contains approved markers: `INTERNAL-CANARY-NOTICE-v1`, `hr_task_only`, `personal_photo`, `privacy@wathefni.ai`, Hostinger/B2/Vercel, 46-day backup wording, excluded Civil ID/bank details/push/store/channels.

---

## Post-R1B eligibility (read-only)

| Check | Result |
|---|---|
| Company binding `WATHEFNI` | pass |
| `employment_status=active` | pass |
| Unique verified phone | pass |
| Zero invites | pass |
| Zero sessions | pass |
| Cross-company conflict | none |
| `employee_app` modules enabled | **0** (intentional) |
| Eligible now | **yes** |

---

## Still incomplete before final GO

1. Rollback owner with proven technical production access (not Fouad; Aziz currently blocked by bootstrap auth)  
2. Activation-window availability confirmation (first four hours)  
3. Mailbox human receive + monitoring acknowledgment  
4. Fouad explicit consent + notice acknowledgment  
5. Separate final execution GO phrase

## Not done (correctly held)

- company `employee_app` module enablement  
- global `WATHEFNI_EMPLOYEE_APP`  
- onboarding row  
- invite / session / activation material  
- canary execution  

Protected flags remain OFF: employee app, company channel accounts, onboarding seed. Push and external activation delivery remain OFF; activation mode remains `hr_task_only`.
