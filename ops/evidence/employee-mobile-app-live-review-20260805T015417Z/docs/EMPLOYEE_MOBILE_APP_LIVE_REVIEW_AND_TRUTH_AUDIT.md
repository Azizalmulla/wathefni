# Employee Mobile App — Live Review & Implementation Truth Audit

**Stamp:** `20260805T015417Z`  
**App:** `apps/wathefni-employee-mobile` (Expo 51 / RN 0.74 · `ai.wathefni.employee`)  
**Scope:** Inspect only · no redesign · no store submit · Talal canary / production backend boundaries preserved  
**Evidence:** `ops/evidence/employee-mobile-app-live-review-20260805T015417Z/`  
**Prior API canary:** `ops/evidence/employee-mobile-app-qual-20260805T014204Z/` (`TALAL_EMPLOYEE_APP_CANARY_OK`)

---

## 1. Internal preview builds

| Platform | Result | Identifier / blocker |
|---|---|---|
| **iOS** | **BLOCKED** — no installable preview produced | Exact blockers below |
| **Android** | **BLOCKED** — no installable preview produced | Exact blockers below |

### Exact blockers (stop here — not store-readiness work)

1. **EAS auth:** `npx eas-cli whoami` → `Not logged in` (no Wathefni Expo owner session on this machine).
2. **EAS project:** `app.json` → `expo.extra.eas.projectId` = `REPLACE_WITH_EAS_PROJECT_ID`.
3. **Assets:** no `assets/` directory; `icon` / `splash` / `android.adaptiveIcon` unset in `app.json`.
4. **Local native toolchain:** Xcode is Command Line Tools only (`simctl` unavailable); `ANDROID_HOME` unset.
5. **Profiles:** `eas.json` `preview`/`development` point at **staging** API; `production` points at `https://api.wathefni.ai` with push off. Even after login, a Talal-canary physical install needs a **production-profile** (or preview env override to prod) build — still blocked by (1)–(3).

**Unblock order (owner only):** `eas login` → `eas init` (real projectId) → add approved icon/splash → register devices → `eas build --profile production --platform ios|android` (internal distribution) → install on Talal test devices.

No unrelated store assets, privacy publishing, or FCM work was started in this audit.

---

## 2. Screen-by-screen PASS/FAIL (implementation truth)

Data class: **live production `/app/*`** unless noted. No demo/static module payloads found in screens.

| Screen | Verdict | Live data? | APIs | Mutations / authority | Auto-refresh | Incomplete / hidden |
|---|---|---|---|---|---|---|
| Login / activation | **PASS** | Live | `POST /app/auth/request-code`, `POST /app/auth/activate` → `GET /app/me` | Activate only; allowlist enforced server-side | N/A | `+965` chip UI-only (not auto-prepended) |
| Session expiry / refresh | **PASS** | Live | `GET /app/me`, `POST /app/auth/refresh` | Session-bound; 401 → refresh once | Cold start + AppState `active` refresh `me` | Query cache **not** cleared on logout |
| Logout | **PASS** | Live | `POST /app/push/unregister`, `POST /app/auth/logout` (best-effort) | Clears SecureStore | N/A | Errors swallowed |
| Home | **PASS** | Live | `GET` notifications, shifts/today, attendance, leave, onboarding (feature-gated) | Read-only | `staleTime` 30s; **no** focus refetch; **no** PTR | Unused `HomeLoadingView`/`HomeErrorView`; documents only as quick-nav |
| Profile | **PASS WITH FINDINGS** | Live (`/app/me`) | No screen query; uses AuthProvider | Sign-out only | AppState me only | No email / onboarding_status; no `/app/profile` call; no edit |
| Attendance | **PASS** | Live | `GET /app/attendance` ← `attendance_records` | **View only** (`actions: view`) | 30s stale | **No clock in/out** in app (by contract) |
| Leave list / cancel | **PASS** | Live | `GET /app/leave` ← `leave_requests` + balances; `POST /app/leave/{id}/cancel` | Cancel if `can(leave,cancel)` + status requested/approved; ownership guard | Invalidate `['leave']` after cancel | Balances observe-only footnote |
| Leave request | **PASS WITH FINDINGS** | Live | `POST /app/leave/request`; types from `me.leave.types` | `can(leave,request)`; self-scope key check | Invalidate leave | Manual `YYYY-MM-DD` text (no picker) |
| Shifts | **PASS** | Live | `GET /app/shifts/today`, `/upcoming` ← `shift_assignments` | View only | 30s stale | No swap/accept; today error masks upcoming |
| Onboarding | **PASS WITH FINDINGS** | Live | `GET /app/onboarding`; `POST /app/onboarding/documents` | Upload if `can_upload` + document item; ownership on `onboarding_items` | Invalidate onboarding+documents after **own** upload | No due dates; optional-only rows omitted by API; “rejected” UX mostly orphaned vs compliance reject |
| Documents / compliance | **PASS WITH FINDINGS** | Live | `GET /app/documents`; download; `POST /app/documents/renew` | View/download/renew via features | Invalidate after renew | OCR/versions typed but not rendered; `compliance_actions` feature reserved/disabled |
| Notifications | **PASS** | Live | `GET /app/notifications`; `POST .../read` | Mark-read | Invalidate after read | Mark-read errors swallowed; push deep-link → notifications tab |
| Settings | **PASS WITH FINDINGS** | Live mutations | Push register/unregister; `POST /app/account/request-deletion` | Push only if env=1 **and** `manage_push` | N/A | Locale **client-only** (`change_locale` unused); push no-ops without real EAS projectId |
| Privacy / support | **PASS (static)** | Static links | None | Opens privacy URL / mailto | N/A | No in-app policy body |
| EN / AR / RTL | **PASS WITH FINDINGS** | — | — | — | — | RTL flip needs restart alert; no `expo-updates` auto-reload |
| Offline / loading / empty / error | **PASS WITH FINDINGS** | — | — | — | — | Offline escalates to AuthGate access state; no PTR; no dedicated stale banner |
| Payslips / payroll | **PASS (absent by design)** | — | — | `payslips` `implemented: False` | — | No route/UI |
| Hiring / HR admin | **PASS (absent)** | — | — | Not in employee app | — | — |

---

## 3. Onboarding web ↔ mobile synchronization

### Authoritative model

```
Web PostHire Onboarding          Employee mobile
  GET/POST dashboard/posthire/*    GET/POST /app/onboarding*
              │                         │
              └──── wathefni-orchestrator ────┘
                         │
         onboarding_items + employee_onboarding_assignments
         + employees.onboarding_status
         + employee_documents / file_registry
```

Canonical read: `employee_onboarding_summary` / `load_onboarding_items`  
Template: `default_kuwait@2.0.0` (Wave2)  
HR mutations: `start_onboarding`, `onboarding_mark_item`, `cancel_onboarding`, `reschedule_onboarding`, reminders  
Employee mutation: upload → item `status='received'` (ownership JOIN employees)

### Two-way matrix

| Criterion | Result | Notes |
|---|---|---|
| HR create / start → mobile sees | **PASS** | Same tables; mobile after refetch |
| HR edit due / order / required docs → mobile | **FAIL (capability missing)** | No HR patch API for due/order/requiredness; dues from seed/reschedule only |
| Mobile upload / complete → web sees | **PASS (on refresh)** | Shared rows; HR must reload detail |
| HR cancel / mark received / waive → mobile | **PASS (on refetch)** | Same rows; mobile may stay stale ≤30s |
| HR reassign checklist | **FAIL** | No reassign action |
| No app-only shadow checklist | **PASS** | No mobile-only checklist table (`onboarding.json` side write unused by readers) |
| Duplicate / idempotent upload | **PASS WITH FINDINGS** | Seed/start/cancel idempotent; upload has **no** client idempotency key (overwrite same item) |
| Cross-client live invalidation | **FAIL** | No shared realtime; each side invalidates only after own mutation |
| Web-only fields | — | due_date, sort_order, owner, depends_on, row_version, reminders, optional open items |
| Mobile-only fields | — | Upload progress / cancel transfer; localized known item labels |

**Overall sync:** data-layer **PASS**; live UX sync **PARTIAL**.

---

## 4. API / database / source mapping

| Mobile surface | Endpoint | Primary tables / sources |
|---|---|---|
| Identity | `/app/me`, `/app/profile` | Session → `employees`; features from module contract |
| Onboarding | `/app/onboarding`, `POST .../documents` | `onboarding_items`, assignments, `employee_documents`, `file_registry` |
| Leave | `/app/leave`, request, cancel | `leave_requests`, `leave_policies` (types), balance helper |
| Shifts | `/app/shifts/today|upcoming` | `shift_assignments` |
| Attendance | `/app/attendance` | `attendance_records` (30-day window) |
| Documents | `/app/documents`, renew, file | Employee docs + Kuwait compliance journey helper |
| Notifications | `/app/notifications`, read | Inbox rows (employee-scoped) |
| Auth | activate / refresh / logout | `employee_app_invites` / sessions |
| Push | register / unregister | Push tokens (prod registration forced off) |

All `/app/*` queries scoped by `employee_app_context` → fixed `company_code` + `employee_key` (client must not supply employee identity).

---

## 5. Tenant / permission / security findings

| Check | Result |
|---|---|
| Tenant isolation | **PASS** — session company; module + lifecycle gates |
| Employee-level scoping | **PASS** — leave cancel ownership; onboarding item JOIN; leave request key mismatch rejected |
| Capability gates | **PASS** — `require_employee_app_feature` + client `hasFeature`/`can` |
| Allowlist (Talal) | **PASS** — `assert_employee_app_allowlisted`; non-allowlisted → `employee_app_not_allowlisted` |
| Cross-employee / cross-company exposure | **PASS** (contract) — no client-chosen employee_key on `/app/*` |
| Payroll money authority | **PASS blocked** — payslips unimplemented; no money UI |
| Hiring / HR-admin in app | **PASS absent** |
| Mutation idempotency | **MIXED** — leave/ownership guarded; onboarding upload no idempotency key; leave request no client double-submit lock beyond `busy` |
| Bank plaintext via onboarding upload | **PASS blocked** — `bank_via_ess_required` |

---

## 6. UI / UX / rendering findings (no changes)

Aligned with frozen Phase 9A design system (`docs/DESIGN_SYSTEM.md`): cream `#F8F2E8`, ink `#1C1B19`, pastel module cards, Newsreader / Noto Kufi wordmarks, capability-driven surfaces.

| Theme | Finding |
|---|---|
| Philosophy | **Mostly matches** — employee-first home (“today at work”), not an HR dashboard; clear next action via onboarding attention card |
| Clutter | Home can stack attention + caught-up + module grid + progress + quick actions (mild duplication of onboarding/leave CTAs) |
| Cream/ink | **PASS** — tokens match foundation; restrained accent `#AA477F` |
| Navigation | Stack + tabs coherent; feature tabs hide via `href: null` |
| Refresh UX | **Weak** — no pull-to-refresh; `refetchOnWindowFocus: false`; HR changes invisible until 30s stale expires or remount |
| Forms | Leave dates as plain text — friction / validation risk |
| RTL | Direction flips with restart requirement |
| Overlays / remount | No stuck overlay found in code; logout leaves react-query cache (stale flash risk on re-login as same device) |
| Device performance | **Unverified** — no physical install this stamp |

---

## 7. Automatic-refresh behavior (current)

| Trigger | What refreshes |
|---|---|
| App foreground | `GET /app/me` only |
| React Query | `staleTime` 30s; `retry` 1; **no** window-focus refetch |
| After own mutations | Leave / onboarding upload / documents renew / notification read → targeted `invalidateQueries` |
| Pull-to-refresh | **None** |
| Push-driven list refresh | Deep link to notifications tab only; no automatic inbox refetch beyond invalidate on mark-read |
| Cross-client (web↔mobile) | **None** |

---

## 8. Critical blockers

1. Cannot produce signed internal iOS/Android previews (EAS login + projectId + assets + native toolchain).
2. Physical-device live review blocked until (1).
3. Onboarding live sync incomplete: no PTR/focus refetch; no due dates on mobile; no HR edit-due/order API; rejected-state wiring weak.
4. Production push intentionally off; Settings push requires real EAS projectId even when enabled.

---

## 9. Recommended refinement order (awaiting approval — do not implement yet)

1. Owner: EAS login + real projectId + icon/splash → **production-profile internal builds** for Talal devices.  
2. Pull-to-refresh + refetch-on-focus for home/onboarding/documents/leave (low-risk client).  
3. Onboarding truth: surface `due_date` if returned; align rejected guidance with compliance status or drop orphan copy.  
4. Leave date picker (or validated native input).  
5. Clear QueryClient on logout.  
6. Only then: broader polish (home CTA de-dupe, optional items policy, SDK upgrade) — still no redesign, no allowlist expansion, no payroll.

---

## 10. GO / NO-GO (this stamp)

| Decision | Result |
|---|---|
| Continue Talal API canary | **GO** (prior `TALAL_EMPLOYEE_APP_CANARY_OK`) |
| Live device review with installable builds | **NO-GO** until EAS blockers cleared by owner |
| Broad refinement implementation | **NO-GO** until live inspect + approval |
| Store submission | **NO-GO** |
| Allowlist / backend contract / payroll changes | **NO-GO** |
