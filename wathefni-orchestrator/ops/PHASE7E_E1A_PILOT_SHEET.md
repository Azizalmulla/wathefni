# Phase 7E — E1a Pilot selection / readiness sheet

**Status:** Approved and locked for E2. Not an enablement approval.  
**Date:** 2026-07-12  
**Phase boundary:** No production company create/activate. No flag flips.  
**Protected flags (unchanged):** `WATHEFNI_EMPLOYEE_APP=off`, `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`, `WATHEFNI_ONBOARDING_SEED=off`

---

## A. Purpose of this sheet

This sheet names:

1. The **staging validation target** for E2 (throwaway only)  
2. A **proposed production pilot profile** for a future Phase 8 decision  

It does **not** create production records, enable modules in production, issue invites, or flip flags.

---

## B. Staging validation company (E2 only — not the production pilot)

| Field | Value |
|-------|--------|
| Company code | `P7ESTG01` (throwaway; created only during approved E2 staging window) |
| Environment | Staging DB / staging orchestrator only |
| Existing related staging tenants (reference only) | `V2STAGEDRY01` (active, 0 employees, has `employee_app` configured historically); `P7ASTG01` (archived); staging `WATHEFNI` (exists — **do not use as 7E pilot target**) |
| Action in E1 | **None** — do not create `P7ESTG01` until E2 is approved |

---

## C. Proposed production pilot profile (Phase 8 intent only)

| Field | Proposed value |
|-------|----------------|
| One pilot company | **TBD — not created in 7E.** Working label: `PROPOSED_PILOT_CO` (replace with real consenting client code only in Phase 8 RFC). **Do not use production `WATHEFNI` unless a separate written decision names it as the pilot and accepts support load.** |
| Qualification reason | First closed, HR-provisioned employee-app pilot on **shared platform WhatsApp** after E2 matrix green; company must already run post-hire modules needed for included workflows; prefers employees with phones already on file and **manually provisioned** onboarding checklist items (Option A). |
| Small cohort size | **Max 5 employees** for first production pilot window (recommend start with 3). |
| HR owner | **TBD** — named client HR admin who will issue app invites and handle deletion requests. |
| Rollback owner | **Wathefni platform operator** (same role as prior dark-launch operators) — authorized to remove `WATHEFNI_EMPLOYEE_APP` drop-in and/or disable `company_modules.employee_app` for the pilot company. |
| Included workflows | 1) HR invite + employee activate 2) Profile / me 3) In-app notification inbox (read/mark) 4) Onboarding checklist **view + document upload** (Option A items only) 5) Leave balance / request / cancel (if `leave` module enabled for pilot) |
| Excluded workflows | Push notifications (first window = **inbox-only** unless Phase 8 expands) · Company-owned WhatsApp (7D remains production-dark) · Onboarding seed (`ONBOARDING_SEED` stays off) · Payroll / assessments / video interview surfaces · Public App Store / Play listing · Multi-company enablement · Production WATHEFNI as default guinea pig |
| Outbound mode | **Inbox-only for ongoing notifications** in the first pilot window. **Activation codes** may use existing shared WhatsApp session and/or email ladder, or surface as `hr_task` if nothing lands — never invent “delivered.” |
| Onboarding mode | **Option A** — checklist rows must be **manually and explicitly provisioned** per pilot employee before invite. Empty checklist ≠ completed. |
| Success criteria | ≥80% of cohort activates within 7 days · ≥1 successful document upload per participating employee with checklist items · Zero cross-tenant or cross-employee data incidents · Kill-switch drill executable in &lt;15 minutes · All delivery UI states match server outcomes · No need to enable 7D or seed to make the pilot work |
| Stop criteria | Silent invite delivery failure without `hr_task` / failed state · Any cross-tenant/cross-employee leak · Support load exceeds HR owner capacity · Crash / unblockable 5xx on `/app/*` for active cohort · Pressure to enable `COMPANY_CHANNEL_ACCOUNTS` or `ONBOARDING_SEED` to “unstick” the pilot · Rollback owner unavailable |

### Explicit 7E prohibitions (reconfirmed)

- [x] No production pilot company creation in Phase 7E  
- [x] No production `employee_app` module enablement in Phase 7E  
- [x] No production invites / activations in Phase 7E  
- [x] No production flag enablement in Phase 7E  

---

## D. Cohort planning notes (no PII in git)

| Item | Plan |
|------|------|
| Cohort phones | Held only in operator runbook / HR sheet outside git; count only here (max 5) |
| Checklist provisioning | For `P7ESTG01`, E2 manually creates exactly four canonical employee-actionable items — `civil_id`, `personal_photo`, `employment_contract`, `bank_details` — and uses synthetic files only. Production pilot items remain a Phase 8 company decision. |
| Excluded employees | Anyone without a verified phone; anyone already `left`; anyone lacking Option A checklist if onboarding is in scope |

---

## E. Locked E2 inputs

1. Staging target is `P7ESTG01`; companion throwaway employees/tenant fixtures may be created only as needed for isolation proofs.  
2. Production pilot company remains **TBD** until Phase 8 and must not default to `WATHEFNI`.  
3. Proposed cohort cap is **5**; no production cohort is created or activated in Phase 7E.  
4. First pilot mode is inbox-only for ongoing notifications. Activation may use only the existing shared delivery ladder and `hr_task`. Push and company channel accounts are excluded.  
5. Option A is mandatory: `P7ESTG01` receives the four explicit canonical checklist rows above while `WATHEFNI_ONBOARDING_SEED=off`.  
6. E1a and E1b are accepted; E2 verifier-first work is authorized. Application failures must be reported before any remediation.
