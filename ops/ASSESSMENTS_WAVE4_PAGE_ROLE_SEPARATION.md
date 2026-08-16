# Assessments Wave 4 — Page Structure & Role Separation

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260728T030247Z`  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Preserved:** Waves 1–3, scoring, lifecycle, actions, backend truth, report presentation

---

## Final verdict

**PASS — Wave 4**

Daily HR Assessments work is now separated into **Send / Attempts / Reports**. Setup, authoring workbench, publishing controls, kill-switch status, production/non-production warnings, and AI governance/internal technical notices are hidden from normal HR and gated to admin roles. Backend permission gating still denies authoring without `assessment.manage`. Direct links/refresh/Back preserve tab/cohort context, and “Open” now lands in the attempt context instead of the generic candidate profile.

---

## Page structure (HR)

| Tab | Content |
|---|---|
| Send | Cohort queues (Send / Resend / Delivery failed / In progress / Sent pending) |
| Attempts | Recent attempts with status, score, review, resend/cancel/report actions |
| Reports | Completed reports ready for review |

Admin-only (hidden for normal HR): Assessment setup, setup details, `Product2AuthoringPanel` (authoring workbench), kill-switch / non-production / governance messaging.

## Role rules

| Role | Access |
|---|---|
| Recruiter | Send, Attempts, Reports (no setup/authoring) |
| Hiring manager | Attempts and Reports, limited sending where permitted (no setup/authoring) |
| HR admin | Operational page + setup |
| Company admin | Setup/authoring |
| Super admin | All |

`canSeeSetup = assessment.manage && role not in {recruiter, hiring_manager}`. Normal HR never sees technical controls they cannot use.

---

## Navigation

- Dedicated Send / Attempts / Reports tabs with stable `tab` URL state.
- Cohort URLs (`assessment_cohort` / `tab`) preserved (Wave 3 durability).
- Refresh/Back keep context.
- “Open” from queue and attempts routes to the **Attempts** context (attempt-centric), not the generic candidate profile.
- View report still resolves via the assessment report path; full first-class report page redesign is the next wave.

---

## Proof (`20260728T030247Z`)

| Assertion | Result |
|---|---|
| Clean role separation (recruiter/hiring_manager see no setup/authoring) | **PASS** |
| No technical/admin content on normal HR page | **PASS** |
| Permissions enforced backend + frontend | **PASS** (`authoring_denies_without_manage`) |
| Direct links/refresh/Back | **PASS** (URL tab/cohort preserved) |
| Open → attempt context | **PASS** |
| EN/AR + RTL | **PASS** |
| Health 200 | **PASS** |
| Rollback / restore | **PASS** |
| No unrelated mutations | **PASS** |

Evidence: `permission-proof.json` in the stamp directory. Dashboard asset: `dashboard-D9efR1Q2.js`.

---

## Rollback / restore

| Step | Result |
|---|---|
| Dashboard rollback → previous asset | `dashboard-DClPrDhC.js`; health **200** |
| Dashboard restore → Wave 4 asset | `dashboard-D9efR1Q2.js`; health **200** |

---

## Remaining limitations

- A dedicated “Assessment administration” page is not a separate route yet; admin content is hidden from normal HR rather than moved to its own screen.
- View report still uses the existing report view; a first-class in-app report page is the next wave.
- Attempt context is the Attempts tab (not yet a dedicated per-attempt drawer/workspace).
- Hiring-manager send granularity beyond `assessment.manage` is not separately modeled.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| HR page only Send/Attempts/Reports | **PASS** |
| Setup/authoring/admin controls hidden from normal HR | **PASS** |
| Role rules enforced | **PASS** |
| Backend permission denial for authoring | **PASS** |
| Direct links/refresh/Back | **PASS** |
| Open → attempt context | **PASS** |
| EN/AR + RTL | **PASS** |
| Health 200 + rollback/restore | **PASS** |
| No unrelated mutations | **PASS** |

**Stop after Wave 4.**
