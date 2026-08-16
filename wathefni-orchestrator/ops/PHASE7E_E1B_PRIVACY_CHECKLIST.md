# Phase 7E — E1b Privacy / store readiness checklist

**Status:** Approved with §13 decisions locked. Not an enablement approval.  
**Date:** 2026-07-12  
**Sources:** `apps/wathefni-employee-mobile/docs/PRIVACY.md`, `STORE_REVIEW.md`, `ROLLOUT.md`, `app.json`, `eas.json`, `package.json`, `app/settings.tsx`, orchestrator `/app/*` + outbound delivery.  
**Protected flags (unchanged):** `WATHEFNI_EMPLOYEE_APP=off`, `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`, `WATHEFNI_ONBOARDING_SEED=off`

Legend for each item:

| Tag | Meaning |
|-----|---------|
| **CONFIRMED** | Current code/docs behavior |
| **MISSING DECISION** | Policy/product choice still needed |
| **TECH BLOCKER** | Must fix before the named track |
| **STORE BLOCKER** | Blocks App Store / Play (or external TestFlight / closed testing) |
| **NOT REQUIRED (staging)** | Not required for internal staging / E2 throwaway validation |

---

## 1. Privacy policy URL & hosting

| Item | Classification | Notes |
|------|----------------|-------|
| Draft policy text exists | **CONFIRMED** | `docs/PRIVACY.md` — marked DRAFT; employer = controller, Wathefni = processor |
| In-app Settings link target | **CONFIRMED** | `PRIVACY_URL = https://wathefni.ai/employee-app/privacy` in `app/settings.tsx` |
| Page actually published at that URL | **STORE BLOCKER** | The AI developer prepares technical inventory/draft; the Wathefni product owner/operator approves and publishes. Not required for E2 staging. |
| Legal sign-off on controller/processor wording | **MISSING DECISION** | Especially Kuwait/GCC employment + processor clauses |
| Required for internal staging / E2 API matrix | **NOT REQUIRED (staging)** | E2 is backend/API + throwaway; no store track |

---

## 2. Data collected (declare accurately)

| Data | Classification | Notes |
|------|----------------|-------|
| Phone + name | **CONFIRMED** | Used for activate + profile; from employer HR records |
| Employment surfaces (onboarding, shifts, attendance, leave, documents list) | **CONFIRMED** | Read from employer workspace via `/app/*` |
| Uploaded documents (user content) | **CONFIRMED** | Employee-chosen files to HR |
| Push token | **CONFIRMED** | Registered via `/app/push/register` when permission granted; optional |
| Device platform + app version | **CONFIRMED** | Documented in PRIVACY.md; used for delivery/support |
| Location / contacts / mic / advertising ID | **CONFIRMED** absent | No collection; permissions not requested for these |
| Third-party analytics / ad SDKs in app deps | **CONFIRMED** absent | `package.json` has no Sentry/Amplitude/Segment/Firebase Analytics; PRIVACY claims no ad trackers |
| Exact retention periods (days/years) per data class | **MISSING DECISION — PHASE 8** | No automatic hard deletion for staging/internal readiness. Final production-pilot SLA is a Phase 8 decision. |
| Whether push tokens are deleted on logout vs revoke-only | **MISSING DECISION** (partially **CONFIRMED**) | Revoke path deactivates push tokens on offboarding; confirm logout/unregister coverage in E2 |

---

## 3. Document categories

| Item | Classification | Notes |
|------|----------------|-------|
| Upload allowlist | **CONFIRMED** | `.pdf,.jpg,.jpeg,.png,.webp,.heic`; max **15 MiB** |
| Upload tied to existing onboarding `item_id` | **CONFIRMED** | Cannot invent checklist rows; Option A must pre-provision |
| Which item types E2 will use | **CONFIRMED** | `P7ESTG01`: manually provision `civil_id`, `personal_photo`, `employment_contract`, `bank_details`; synthetic files only. Production pilot set is a Phase 8 company decision. |
| Whether compliance expiry docs are in-app editable | **CONFIRMED** limited | App upload is onboarding-checklist path; broader compliance Hub is HR-side |
| Required for staging E2 | Prove allowlist + ownership; category list can use fixtures | **NOT REQUIRED (staging)** to finalize client doc catalog |

---

## 4. Retention / deletion

| Item | Classification | Notes |
|------|----------------|-------|
| Employment records retained per employer | **CONFIRMED** posture in draft policy | |
| In-app “delete account” = HR request, not self-wipe | **CONFIRMED** | `POST /app/account/request-deletion` → HR task |
| Staging/internal deletion posture | **CONFIRMED** | No automatic hard deletion. Employee revoke and company disable/archive immediately remove access. Deletion/retention requests create an auditable HR task. Actual deletion requires authorized HR/admin action plus file/metadata reconciliation. |
| Final deletion/retention SLA | **MISSING DECISION — PHASE 8** | Required for the production-pilot policy and external review wording. |
| Session TTL | **CONFIRMED** | Access ~7 days; refresh longer (orchestrator constants); invite TTL **24h** |
| File retention after employee `left` | **MISSING DECISION** | API access revoked; underlying Document Hub retention policy not finalized in privacy draft |
| Required for internal staging | Revoke blocks API; full legal retention schedule | **NOT REQUIRED (staging)** for E2 green |

---

## 5. Employee account closure

| Item | Classification | Notes |
|------|----------------|-------|
| Request path in Settings | **CONFIRMED** | Implemented |
| Sessions/tokens revoked on employment inactive / offboarding helper | **CONFIRMED** intent | `revoke_employee_app_access`; context rejects non-active employment |
| Company lifecycle (disable/archive) enforced on every `/app/*` request | **TECH BLOCKER** for plan §3 completeness | Today `employee_app_context` checks flag + module + session + employment status; **company lifecycle gate must be verified/fixed in E2** if missing — do not treat UI hide as sufficient |
| Store reviewer explanation (controller model) | **CONFIRMED** draft in STORE_REVIEW | **STORE BLOCKER** until privacy URL + reviewer demo exist for external tracks |

---

## 6. Support contact

| Item | Classification | Notes |
|------|----------------|-------|
| Privacy contact email in policy | **STORE BLOCKER** | Use a dedicated role-based Wathefni privacy/support mailbox, never a personal operator address. Exact mailbox may remain unresolved for staging but must be set before publication/external pilot. |
| Escalation: employee → employer HR → Wathefni | **CONFIRMED** draft posture | |
| Required for staging E2 | **NOT REQUIRED (staging)** | |
| Required before external testing track | **STORE BLOCKER** (policy completeness) | |

---

## 7. Permissions

| Permission | Classification | Notes |
|------------|----------------|-------|
| Notifications | **CONFIRMED** | Optional; inbox works without |
| Camera / Photos | **CONFIRMED** | Just-in-time on upload; usage strings in `app.json` |
| Android `POST_NOTIFICATIONS` / media | **CONFIRMED** declared | |
| Location etc. | **CONFIRMED** not requested | |

---

## 8. Analytics / crash tools

| Item | Classification | Notes |
|------|----------------|-------|
| Third-party product analytics | **CONFIRMED** none in dependencies | |
| Crash reporter (Sentry, etc.) | **CONFIRMED** none wired | |
| Expo / EAS build telemetry | **MISSING DECISION** | Confirm whether EAS/Expo account telemetry is acceptable to disclose; not an in-app tracker |
| `console.*` stripped in production builds | **CONFIRMED** | babel plugin per STORE_REVIEW |
| Required for staging | **NOT REQUIRED (staging)** | |

---

## 9. External provider sharing

| Provider / channel | Classification | Notes |
|--------------------|----------------|-------|
| Hosting / Postgres / API (`api.wathefni.ai` / staging) | **CONFIRMED** | Employment data processed on Wathefni infra |
| Expo Push relay (+ Apple/Google push) | **CONFIRMED** when push enabled | Token shared with Expo/APNs/FCM path; push optional for inbox-only pilot |
| Shared WhatsApp (Octopus / openclaw path) | **CONFIRMED** for activation ladder when used | Company channel accounts **not** used (7D dark) |
| Email provider (Postmark/etc. if configured) | **CONFIRMED** as ladder fallback when configured | |
| Document storage (local default / optional Drive) | **CONFIRMED** | Same as HR upload pipeline |
| Factual subprocessor inventory | **MISSING DECISION — PHASE 8 EXTERNAL BLOCKER** | Inventory only actually deployed infrastructure, storage, messaging/email, monitoring, and AI providers. Do not invent providers or confirm generic boilerplate. AI developer prepares inventory/draft; product owner/operator approves wording. |

---

## 10. Store / build technical blockers

| Item | Classification | Notes |
|------|----------------|-------|
| EAS `projectId` still placeholder | **TECH BLOCKER** for push · **STORE BLOCKER** for push-enabled builds | `app.json` → `REPLACE_WITH_EAS_PROJECT_ID`; inbox-only works without |
| App icon + splash assets | **STORE BLOCKER** | No `assets/` shipped; Expo placeholders |
| `EXPO_PUBLIC_API_BASE_URL` per profile | **CONFIRMED** in `eas.json` | development/preview → `https://staging-api.wathefni.ai`; production → `https://api.wathefni.ai` — **verify DNS/edge** before builds |
| Bundle IDs | **CONFIRMED** | iOS `ai.wathefni.employee`; Android `ai.wathefni.employee` |
| Account deletion path | **CONFIRMED** | |
| Reviewer demo account process | **MISSING DECISION** (ops) | Who issues 24h codes during review |
| Required for internal staging / E2 | **NOT REQUIRED (staging)** | E2 does not need TestFlight |
| Required for Phase 8 external pilot track | **STORE BLOCKER** set above | |

---

## 11. Outbound delivery honesty (privacy-adjacent / product)

| Item | Classification | Notes |
|------|----------------|-------|
| Activation delivery uses shared outbound ladder | **CONFIRMED** | `deliver_app_activation_code` → `deliver_employee_notification`; failure can yield failed status / HR task path |
| Canonical UI vocabulary: created / attempted / delivered / failed / suppressed / fallback | **CONFIRMED POLICY** + **TECHNICAL PROOF REQUIRED** | Backend owns the states; UI may display only backend-provided state and must not invent delivered. |
| First pilot notification mode | **CONFIRMED** | Ongoing notifications are inbox-only; push excluded. Activation may use the existing shared delivery ladder and `hr_task`. Company channel accounts are not required. |
| Required for E2 | Prove server states under dry-run/mocked sends; no fabricated client delivery | |

---

## 12. What is required vs not for tracks

### Internal staging / E2 (`P7ESTG01`) — required now

- Authorization / invite / upload / revoke proofs (E2)  
- Option A honesty (empty ≠ complete)  
- Delivery state honesty under dry-run  
- No production flag changes  

### Internal staging — **not** required

- Published privacy URL  
- Store icons/splash  
- Real EAS projectId (unless testing push)  
- Legal contact email filled  
- Customer DPA pack  
- Production pilot company  

### External TestFlight / Play closed testing — required later (Phase 8+)

- Published privacy URL + Settings match  
- Support/privacy contact  
- Icons/splash  
- EAS projectId if push in scope  
- Reviewer invite runbook  
- Retention/deletion SLA wording signed off  

### Public store listing — later still

- Full listing copy, screenshots, broad localization QA  

---

## 13. Locked decisions

1. **Privacy contact:** dedicated role-based Wathefni privacy/support address; exact mailbox can remain unresolved for staging but blocks publication/external pilot.  
2. **Retention:** no automatic hard deletion for staging/internal readiness; revoke and company disable/archive remove access immediately; deletion/retention requests create an auditable HR task; authorized HR/admin performs actual deletion with file/metadata reconciliation; final SLA moves to Phase 8.  
3. **E2 document set:** `civil_id`, `personal_photo`, `employment_contract`, `bank_details`, manually provisioned on `P7ESTG01`, synthetic files only.  
4. **Subprocessors:** factual inventory from actually deployed providers only; AI developer drafts, product owner/operator approves; final wording required before external pilot, not E2.  
5. **Notifications:** activation through existing shared ladder/`hr_task`; ongoing inbox-only; no push; no company channel dependency; UI displays backend-owned state only.  
6. **Policy ownership:** AI developer prepares technical inventory and draft; Wathefni product owner/operator approves and publishes.

---

## 14. E2 authorization boundary

E1a and E1b are accepted. E2 verifier-first work is authorized against isolated staging fixtures only. Any application gate failure is a reported blocker; application remediation requires separate approval.
