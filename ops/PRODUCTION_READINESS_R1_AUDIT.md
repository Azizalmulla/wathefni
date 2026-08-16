# Production Readiness R1 — Full Surface + Release Blocker Audit

Phase: R1 (audit only — nothing fixed, nothing refactored)
Date: 2026-08-12
Evidence: `ops/evidence/production-readiness-r1-20260812T130753Z/`
Charter: `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
Method: static source audit of all three clients + orchestrator, with every headline claim spot-verified
against source. Nothing was executed against staging or production. No physical device was used.

---

## 1. Executive verdict

**NOT READY for a real company. 7 P0 release blockers, 24 P1 must-fix, 14 P2 polish, 11 PHYSICAL items unproven.**

The single most important finding of R1 is a gap between what the frozen wave stamps assert and what the product
actually exposes:

> **Wave 4 (Performance & Talent) and all seven Wave 6 HCM modules have no HTTP API and no product surface on any
> client.** They exist as Python domain modules, database schema, Setup Console toggles, and smoke tests. A
> company administrator can switch "Job Architecture", "Learning", "Benefits", "Employee Relations",
> "Engagement", "Compensation Planning" or "Workforce Planning" ON in Setup and **nothing appears anywhere** — no
> HR Web page, no HR Mobile route, no Employee App surface, not even an API endpoint to call.

This was verified three ways (§6, P0-1). It is not a nav-gating bug; the code does not exist. The C8
`WAVE6_PRODUCT_FULL_PASS` proved module contracts at library level — it did not prove shipped surfaces, and the
"surface quality" clause of the C8 charter was not actually satisfied by shipped code.

What *is* genuinely solid, and should not be re-litigated:

- Waves 1–3 core operations (employees, onboarding, attendance, leave, shifts, payroll, compliance, documents)
  have real surfaces on HR Web, real employee self-service, and real canonical backend truth.
- Session namespace isolation between employee / HR-operator / browser-dashboard principals is explicitly
  guarded and fail-closed (`operator_mobile.py:1055-1070`).
- Employee App module composition is genuinely module-aware: disabled modules remove tabs (`href: null`), Home
  omits their cards, and deep links land on an explicit unavailable state rather than an empty shell.
- Clean company bootstrap inserts **no** fixture data — only `companies` + `company_settings`.
- Backups exist as a real systemd timer + script + restore runbook + restore drill.
- Mobile EN/AR catalogs are at exact key parity (1300/1300, 222/222, 196/196).

The blockers are concentrated in four places: **inert Wave 4/6 capability**, **authentication and secret
hardening**, **production data-safety of ops scripts**, and **mobile keyboard/native readiness**.

---

## 2. P0 — Release blockers

### P0-1 — Wave 4 and Wave 6 capability is inert: Setup promises modules that do not exist as product

Setup Console mounts a Wave 4 Performance & Talent card and all seven Wave 6 cards, each with an `enabled`
toggle backed by `*_company_settings` tables. Enabling them changes nothing a user can reach.

Verification (all three independently confirm):

1. No HTTP route exists for any of them — `rg '@app\.(get|post|patch)\("/dashboard/[^"]*(job-architecture|learning|benefits|employee-relations|engagement|compensation|workforce-planning)'` returns **zero** matches, and none of the modules is registered through the `register_*_routes(...)` pattern used by every shipped HTTP module (`app.py:45776-45808`, `47062-47074`, `76496-76539`).
2. The Wave 4 and Wave 6 domain modules are imported by **nothing** except `setup_console_wave6_policies.py` and the C8 acceptance module `wave6_hcm_expansion_product_c8.py`. Wave 4 modules (`performance_goals_c1.py` … `talent_succession_c6.py`) match only themselves — no importer at all.
3. No client references them. `apps/wathefni-dashboard/src` (outside `setup-console/`), `apps/wathefni-employee-mobile`, and `apps/wathefni-hr-mobile` all return **zero** matches for job architecture / learning / benefits / employee relations / engagement / compensation planning / workforce planning. The dashboard `Page` union (`types.ts:703-728`) has 25 pages, none of them Wave 4 or Wave 6.

Why P0: a Setup toggle that claims a capability and delivers nothing is fake capability in a production
administrative surface, and it breaks the charter rule that every enableable module must have an intentional
product surface. It also means the HCM expansion cannot be sold or used.

### P0-2 — Forgeable public links: hardcoded HMAC secret fallbacks

`wathefni-orchestrator/app.py:33589-33611`

```
def assessment_link_secret() -> bytes:
    secret = (os.environ.get("WATHEFNI_ASSESSMENT_LINK_SECRET")
        or ... or os.environ.get("WATHEFNI_DATABASE_URL")
        or "wathefni-assessment-dev-secret")
```

`video_interview_link_secret()` is identical with `"wathefni-video-interview-dev-secret"`. Two failures:

- If the dedicated secrets are unset in production, the signing key is a **public constant committed to this
  repository** — anyone can forge assessment and video-interview capability tokens for any candidate in any tenant.
- The fallback chain uses `WATHEFNI_DATABASE_URL` as a signing key. A database connection string containing
  credentials should never be used as key material.

These must fail closed, as `durable_email_ingress.py:2543-2551` already correctly does.

### P0-3 — No authentication rate limiting on web dashboard or Setup Console login

`app.py:45664-45695` (`/dashboard/auth/login`) and `app.py:46979-46999` (Setup operator login) have no attempt
counter, lockout, or cooldown. A repo-wide scan found **no HTTP rate-limiting middleware of any kind**
(`security/rate-limiting.txt`): the only throttles that exist are domain-specific (operator *mobile* login lock
in `operator_mobile.py:166-237`, employee OTP lockout at 5 attempts, reminder caps, Stage B job caps).

Unlimited password spray and tenant/email enumeration against the two highest-privilege login surfaces.

### P0-4 — Internal worker endpoint fails open when its token is unset

`app.py:59036-59044`

```
configured = os.environ.get("WATHEFNI_INTERNAL_WORKER_TOKEN") or os.environ.get("WATHEFNI_INTERNAL_TOKEN")
if configured: ...verify...
client_host = (request.client.host if request.client else "") or ""
if client_host not in {"127.0.0.1", "::1", "localhost"}: raise 403
```

With no token configured, `/internal/video-interviews/process-transcripts` is reachable unauthenticated by
anything that presents as localhost — including any co-located process, and any reverse-proxy misconfiguration
that does not preserve the real client address. Auth that degrades to "no auth" when misconfigured is a P0
pattern regardless of current environment values.

### P0-5 — Cross-tenant-capable internal endpoints take `company_code` from the caller and some are unscoped

- `app.py:82014-82067` — `/orchestrator/audit/turns`, `/pending-actions`, `/action-results` select from
  `hr_turns` with **no company predicate at all**, returning `raw_text` conversation content across every tenant
  in one call.
- `app.py:82419-82631` — debug intake replay / sweep / download / signed-download take `company_code` from a
  query parameter, unbound to any operator's tenant. `?apply=true` on the quarantine sweep **deletes**.
- `app.py:81927-81975` — email-intake accepts `company_code` in the request body and writes.
- `app.py:7545-7550` — `request_company_code` trusts `metadata.company_code` when `channel == "web_dashboard"`,
  so `/orchestrator/whatsapp-turn` can act on any tenant.

All are gated behind `require_internal_access`. Per the charter rule that anything remotely capable of exposing
another tenant is a blocker, these are P0 until each is either tenant-scoped, or explicitly reclassified as
break-glass with audit logging, operator attribution, and a documented control.

### P0-6 — Fixture-injection scripts default to the production database

`ops/ops-seed-*-visual-fixture.py` (inbox, onboarding, payslip, schedule, bank, docs, wave1) each begin with
`os.environ.setdefault("WATHEFNI_ENV", "production")` and production Postgres defaults — e.g.
`ops/ops-seed-inbox-visual-fixture.py:25-47`. `ops/kuwait-pilot-document-journey-production-matrix.py:40-51,103`
does the same and executes `DELETE FROM company_modules` for its synthetic companies.

There is no confirmation prompt, no environment assertion, and no refusal-by-default. A single mistaken
invocation writes fixture employees and messages into, or deletes module configuration from, the production
tenant set. This is the exact class the charter names "production data safety".

### P0-7 — HR Web renders API failure as legitimate empty data

`App.tsx:2809-2810` passes `interviews?.interviews || []` into `InterviewsPage` with no `isError` prop
(`InterviewsPage.tsx:390-391`). A failed fetch is indistinguishable from "no interviews scheduled". The same
pattern appears on the Overview work queue (`OverviewPage.tsx:201-203, 531-575` — failure yields "no personal
work" with no error or retry) and in silent catches in `PostHire.tsx:832-834, 2097-2109, 2131-2132` which turn
failures into empty department, app-access, and pending-status lists.

An HR user who is told "you have no interviews today" when the API is down will miss interviews. Under the
charter this is the fabricated-data class, not a UX nit.

---

## 3. P1 — Must fix before a real customer

**Surface completeness**

| # | Finding | Evidence |
|---|---|---|
| P1-1 | Wave 5 HR Intelligence has no Setup card; KPI enablement, cohort thresholds, fiscal calendar and export policy are env-only, so an admin cannot self-configure it | no `setup_console_wave5_*`; `wave5` absent from module-policies payload `app.py:48585-48679` |
| P1-2 | Wave 4/6 enablement requires Setup toggle **plus** an env flag **plus** an env company allowlist; Setup alone silently fails closed | `setup_console_wave6_policies.py:117-125`, `job_architecture_c1.py:127-153` |
| P1-3 | Wave 4/6 modules are absent from `MODULE_CATALOG`, so Setup's "What this company uses" never lists them | `module_catalog.py` |
| P1-4 | HR Mobile has no Leave list or nav entry — leave approval is reachable only if it happens to appear in Home priorities | `capabilities.ts:43-48` |
| P1-5 | HR Mobile Tasks screen is read-only: `allowedActions` is mapped but never passed as `actionsForItem`/`onAction` | `features/operations/routes.tsx:62-88` |
| P1-6 | HR Mobile dead affordances: document rows (non-compliance), today's shift rows, and destination-less alert rows render a "Review" chevron and do nothing on tap | `routes.tsx:263-269`, `492-494`, `651-654` |
| P1-7 | HR Mobile "Schedule interview" navigates to the interview *list*; there is no scheduling flow | `app/candidates/[appKey].tsx:123` |
| P1-8 | HR Mobile has no candidate filters and no ranking surface — the historically dead hiring paths are still thin | no filter/query-param handling in `routes.tsx:661-698` |
| P1-9 | Employee App preboarding and probation screens are entitled-but-unreachable: real API screens with no tab, Home, or Profile entry, and no push destination | `app/preboarding.tsx:31`, `app/probation.tsx:39`, `employeeAppComposition.ts:13-22`, `resolvePushDestination.ts:14-25` |
| P1-10 | Dashboard delivery-center components are permanently `return null` yet still mounted and lazily exported | `PostHire.tsx:7246-7248`, `NotificationsPage.tsx:799-801`, `pages/lazy.tsx:18-20` |
| P1-11 | "Link to Job" ships disabled with `title="Not implemented in this phase"` in the production governed profile | `CandidateGovernedProfile.tsx:276-281` |

**Permissions and module composition**

| # | Finding | Evidence |
|---|---|---|
| P1-12 | Overview computes `showWorkQueue` / `showRolePriority` but never passes or reads them — the work-queue and role-priority cards mount unconditionally, producing empty cards when those surfaces should be off | `workspaceCapability.ts:460-474` vs `App.tsx:2545+`, `OverviewPage.tsx:460-583` |
| P1-13 | Client-side role fallbacks test role strings that do not exist (`'hr'`, `'admin'` vs real `hr_admin`) on Requisitions, Probation, Preboarding — dead branches masquerading as authorization | `RequisitionsWorkspace.tsx:132-135`, `ProbationWorkspace.tsx:177-184`, `PreboardingWorkspace.tsx:180-181` |
| P1-14 | Alerts & Delivery nav has no permission key; any entitled viewer can open the page (actions are gated, the page is not) | `workspaceCapability.ts:288-294` |
| P1-15 | Restricted-candidates visibility is a client-only role check; server enforcement not evidenced from the client side | `CandidatesTable.tsx:35-44` |
| P1-16 | No global "suppress notification if source module disabled" — gating is per-caller, so any missed call site emits alerts for a disabled module | `deliver_employee_notification` `app.py:19273+` |
| P1-17 | Setup deep links target `?page=migration-sync`, which is not in the dashboard `Page` union — dead Setup→Ops link | `setupConsoleOwnership.ts:126-136`, `OwnershipDeepLinksCard.tsx:49`, `PayrollSetupCard.tsx:322` |
| P1-18 | Duplicate policy ownership: Leave (module-policies card vs Wave 2 card vs `company_modules.settings` overlay), Attendance (three places), Onboarding (Setup auto-start vs env `WATHEFNI_ONBOARDING_SEED`) | `setup_console_modules_phase3b.py:105-261`, `Wave2WorkforceTruthPoliciesCard.tsx:23` |
| P1-19 | 15+ mutations scoped by `employee_key` alone with no `company_code` predicate. Keys are company-prefixed (`app.py:73305`: `f"{company}-{phone_digits}"`) so this is not currently exploitable, but it is one key-format change away from cross-tenant writes | `security/idor-update-scope.txt` (lines 23311, 30693, 37887, 40559-40638, 41008-41912) |

**Security and platform**

| # | Finding | Evidence |
|---|---|---|
| P1-20 | HR Web and Setup Console bearer tokens live in `localStorage`; no httpOnly cookie boundary, and the web dashboard session has no refresh rotation | `App.tsx:288-291`, `setup-console/session.ts:39-65`, `app.py:45101-45132` |
| P1-21 | Non-local documents return the raw provider `storage_url` (Drive `webViewLink`/`webContentLink`) to the client, unproxied and un-re-authorised by Wathefni | `app.py:67232-67236`, `70847-70849`, `23391-23399` |
| P1-22 | Calendar guest token endpoints have no rate limiting (acknowledged in a source comment) | `app.py:44108-44156` |
| P1-23 | No error reporting or crash telemetry anywhere — no Sentry/Rollbar/Bugsnag in orchestrator or any client; `AppErrorBoundary.componentDidCatch` is empty | `infra/infra-inventory.txt`, `AppErrorBoundary.tsx:16-18` |
| P1-24 | No CI: the repository has no `.github` directory and no automated test gate before deploy. Every wave qualification is a manually invoked script | `ls -a .github` → absent |

---

## 4. P2 — Polish debt

1. `App.tsx:282-284, 2357-2368` — dead "Coming soon" nav scaffolding with an empty `futureModuleItems`.
2. `PostHire.tsx:7336-7337` — unknown post-hire page falls through to a blank pane instead of an error state.
3. `PayrollStatutoryArchitecturePanel.tsx:139-159` — "Fixture" column and a raw `permissions manage={true|false}` debug line in production payroll UI.
4. `ShiftsWorkspace.tsx:1162-1171` — Setup nudge banner is permanently visible rather than shown only when policy is missing.
5. `MigrationSyncShell.tsx:877-882` — HR UI can create a `deterministic_canary` connector with a `Math.random()` fixture tag.
6. `apps/wathefni-hr-mobile/app/+not-found.tsx:10-12` — English-only copy, breaks EN/AR parity.
7. `ScheduleWeekStrip.tsx:187` — week pager forces `direction: 'ltr'` while day cells use `row-reverse`; RTL swipe semantics feel inverted.
8. `HomeView.tsx:806-807` — badge positioned with physical `left`/`right` while `swapLeftAndRightInRTL(true)` is active; double-flip risk.
9. `ActivationView.tsx:105`, `RemainingViews.tsx:698-699` — hardcoded `"0000 0000"` and `"Done"/"تم"` outside the i18n catalog.
10. `app/preboarding.tsx:117`, `app/probation.tsx:137` — raw server status tokens rendered as user-facing labels.
11. `app.json:32` — Face ID usage description is English-only in the OS permission sheet.
12. `bank.tsx:112`, `idempotency.ts:2` — `Math.random()` for idempotency keys; weak uniqueness, should be a CSPRNG.
13. `app.py:63670-63683` — Postmark webhook secret accepted via query string (leaks into logs and proxies).
14. `app.py:42142` — `/health` exposes legacy-auth flag state.

---

## 5. Physical-device matrix

Nothing in this matrix can be honestly proven in a browser or from source. All items are currently **UNPROVEN**.
Several are also P1 in code review; observation may escalate them to P0.

| # | Item | Surface | Code-review status | Device verdict |
|---|---|---|---|---|
| PH-1 | Keyboard: active input stays visible | HR Mobile sign-in, leave rejection reason, interview notes | **No `KeyboardAvoidingView` anywhere in the app** — 3 TextInput screens, 0 with keyboard handling (`surfaces/keyboard-coverage.txt`) | UNPROVEN — expected FAIL |
| PH-2 | Keyboard: bottom actions reachable | Employee leave request (multiline reason + date spinner + Submit) | KAV wraps the page but the inner `PageScrollView` does not enable `keyboardInsets` (`RemainingViews.tsx:526-636`, `layout.tsx:71`) | UNPROVEN — high risk |
| PH-3 | Keyboard on Android | All employee + HR forms | Nearly every KAV sets `behavior={undefined}` on Android, i.e. no avoidance | UNPROVEN — expected FAIL |
| PH-4 | Hardcoded keyboard offsets | PIN, HR Assistant | `keyboardVerticalOffset={0}` (`PinView.tsx:85`, `HRAssistantView.tsx:293`) | UNPROVEN |
| PH-5 | Face ID / Touch ID enrol, unlock, fallback, revoke | Employee App | Implemented (Auth Wave 2) | UNPROVEN |
| PH-6 | PIN create / unlock / lockout / recovery | Employee App; HR co-bundle | Implemented; **standalone HR Mobile has no local-lock tree at all** | UNPROVEN + parity gap |
| PH-7 | Native file viewer, camera, uploads | Employee documents, onboarding | Implemented | UNPROVEN |
| PH-8 | Push delivery | All | Expo push implemented | UNPROVEN |
| PH-9 | Push deep links | All | Registry-based; preboarding/probation have no destination mapping | UNPROVEN — known gap |
| PH-10 | Privacy cover, gestures, offline/reconnect | Employee App | Access-gate offline mapping exists; per-module offline copy does not | UNPROVEN |
| PH-11 | Native RTL rendering | All three apps | `I18nManager.forceRTL` + reload implemented; known physical-position risks (§4 items 7–8) | UNPROVEN |

The "parked shared keyboard-safety problem" is confirmed as still open and is now the largest single native
risk: **HR Mobile has zero keyboard avoidance on 100% of its input screens, including sign-in.**

---

## 6. Fake / demo-data inventory

| Item | Location | Classification |
|---|---|---|
| HR co-bundle demo systems: hiring, attendance, shifts, onboarding, documents, tasks, delivery alerts — each with a `*DemoGate` + seeded data (Sara/Noura/Ahmed) | `apps/wathefni-employee-mobile/src/hr/features/*/`, `app.config.js:58-71` | **Dev-only by default, production-capable.** Default `'0'`, but these are production code paths in the shipped binary, switchable by an EAS env value. One mis-set variable replaces live queues with fabricated data. Treat as P1 build-time guard, not test code. |
| HR Mobile design-preview fixtures (Aisha, Lina, Noura, fake scores) | `apps/wathefni-hr-mobile/src/preview/fixtures.ts`, `app/design-preview.tsx` | Dev-only safe — gated on `EXPO_PUBLIC_HR_DESIGN_PREVIEW=1` and web preview |
| `ops-seed-*-visual-fixture.py` writing fixture inbox/onboarding/payslip/schedule/bank/doc rows | `ops/` (7 scripts) | **Production leak blocker** — see P0-6 |
| `kuwait-pilot-document-journey-production-matrix.py` (synthetic companies + `DELETE FROM company_modules`) | `ops/` | **Production leak blocker** — see P0-6 |
| Interviews / Overview / PostHire error-to-empty rendering | `App.tsx:2809`, `OverviewPage.tsx:201`, `PostHire.tsx:832` | **Production leak blocker** (fabricated empty) — see P0-7 |
| Migration Sync `deterministic_canary` connector with `Math.random()` fixture tag creatable from HR UI | `MigrationSyncShell.tsx:877-882` | P2 — synthetic source connection reachable from production UI |
| Payroll statutory panel surfacing `is_architecture_fixture` rows and a permissions debug line | `PayrollStatutoryArchitecturePanel.tsx:139-159` | P2 |
| Leave tab empty-object fallback `{ ok: true, types: [], balances: [], requests: [] }` | `app/(tabs)/leave.tsx:77` | P2 — can present a false "empty leave" state |
| Placeholder identities `'Employee'`, `'Candidate'` when API fields are missing | `app/leave/[id].tsx:78-80`, `normalize.ts:277` | P2 |
| Form example values "Sara Al-Ali" / `96550000000` | `PostHire.tsx:908-918` | Test-only safe — input placeholders |
| `ROLE_PERMISSIONS_FIXTURE`, `*.test.*`, `__tests__` fixtures | dashboard + all apps | Test-only safe |
| Canary identities: `WATHEFNI` default company, Aziz `96599338566`, Talal `WATHEFNI-96550252254`, synthetic prefixes `W5C-SYNTH`, `KWDOCPRD1/2` | orchestrator + ops | Dev-only safe today; must not survive into a real tenant. Note `"WATHEFNI"` is used as a **default fallback company** in several helpers — a missing company code can silently resolve to the canary tenant (P1 class). |

**No** production component was found that substitutes a demo dataset when an API call fails. The fake-data risk
here is not "renders a mock list", it is "renders a confident empty state" plus "ops scripts aimed at prod".

---

## 7. Route / deep-link inventory

**HR Web** — query-param SPA (`?page=`), not React Router. 25 pages in the `Page` union, all present in
`navItems`, no orphan nav targets. Separate Setup Console entry at `setup-console.html`.

| Group | Pages |
|---|---|
| Pre-hire | overview, ai, jobs, requisitions, candidates, interviews, calendar, assessments, ranking, reports, notifications |
| Post-hire | employees, workforce, inbox, preboarding, onboarding, probation, attendance, leave, shifts, payroll, analytics, compliance |
| Platform | activity, settings |
| Setup Console (separate shell) | launch, classic, wizard, control |
| **Missing entirely** | every Wave 4 and Wave 6 domain (P0-1); `migration-sync` is deep-linked but does not exist (P1-17) |

**Employee App** — Expo Router, scheme `wathefni://` only; no `associatedDomains` / Android `intentFilters`, so
there are **no https universal links** (P1 class for email/WhatsApp links).

| Reachable | Tabs: home, schedule, leave, payslips, profile (`href: null` when unentitled) · Pushed: notifications/inbox, settings, change-pin, privacy-support, onboarding, documents, bank, leave/request, leave/history, schedule/history · Auth: activate, PIN, biometric overlays |
| Orphaned | `/preboarding`, `/probation` — implemented, no entry point, no push destination |
| Absent | benefits, learning, engagement, and every other Wave 6 employee surface |

**HR Mobile** — Expo Router Stack (no tab bar); Home is a capability-gated priorities shell. 22 routes.

| Present and functional | Home, Settings, Attendance list + resolve, Leave detail + decision, Shift-swap decision, Candidate shortlist/reject/hire, Compliance document review, Interview notes |
| Present but thin/dead | Tasks (read-only), Documents (non-compliance rows dead), Shifts (row taps dead), Onboarding (review-only), Delivery alerts (destination-less rows dead) |
| Absent | Inbox / Needs Attention, Assistant, employee search UI, hiring filters, ranking, interview scheduling, all Wave 4/6 |

**Deep links** — core ESS destinations (`/payslips`, `/bank`, `/onboarding`, `/documents`, schedule, leave) all
resolve against `APP_ROUTES`. Dead or missing: `?page=migration-sync` (HR Web), preboarding/probation push
destinations (Employee App), and every Wave 4/6 target on all surfaces.

---

## 8. Module-composition matrix

Canonical resolution: `configured_company_modules` (`app.py:3402-3437`) ∩ `module_platform_available`
(`3440-3449`) → `effective_company_modules` (`3452-3486`) → `company_has_module` (`3518-3544`).

| Scenario | Employee App | HR Web | HR Mobile | Verdict |
|---|---|---|---|---|
| Single module (e.g. Leave only) | Tab set collapses cleanly; Home shows only relevant cards | Nav collapses; post-hire landing resolves | Home shows only entitled cards | PASS (design), UNVERIFIED at runtime |
| Two modules | as above | as above | as above | PASS (design), UNVERIFIED |
| Sparse mixed | Deep link to unentitled route → explicit unavailable state | `openPage` remaps disallowed pages (`App.tsx:882-887`) | `routeAvailable` filters priorities | PASS (design) |
| Full suite | — | Overview work-queue and role-priority cards mount unconditionally (P1-12) | — | **FAIL** |
| Module disabled after use | History preserved; disable semantics documented (`setup_console_phase1_ownership.py:21-61`); Employee App revokes sessions/invites | Registry is authoritative once rows exist — cannot be resurrected by legacy metadata | — | PASS with caveat |
| Module disabled after use — inbox | Historical `employee_messages` rows are **not** purged; opening one falls back to Inbox/Home | — | — | **P2 orphan** |
| Notifications for disabled module | Gating is per-caller, not central (P1-16) | — | — | **FAIL (latent)** |
| Wave 4 / Wave 6 enabled | nothing appears | nothing appears | nothing appears | **P0-1** |
| Setup card for unavailable capability | Wave 4/6 cards exist for capabilities with no surface | — | — | **P0-1** |

Additional composition defects: Employee App `MODULE_SURFACES` omits preboarding/probation even though the
features exist on `MeResponse` (P1-9); HR Mobile `ShiftsRoute` renders an empty state rather than
permission-denied when the user lacks capability (`routes.tsx:449-501`); `destinationAvailable` uses exact path
matching, so `/attendance/{id}` and `/documents/...` priority deep links are filtered out as "unavailable"
(`capabilities.ts:115-126`).

---

## 9. Permission matrix

Checked by reading authority code, **not** by issuing requests. Direct-URL and direct-API probing is deferred to
R2 as a live exercise — this is a known limit of R1.

| Role | Menu gating | Server gating evidenced | Findings |
|---|---|---|---|
| Employee | Tab entitlement via `MeResponse` features | `/app/*` resolves identity from `employee_sessions` only; no client-supplied employee/company (`app.py:68416-68495`) | Clean |
| Manager | Scope-based | Manager scope conflicts have explicit codes | Manager ≠ compensation/ER access is contract-level only (no surface exists to test) |
| HR operator | `workspaceCapability` nav | `dashboard_context` derives company from session and rejects `X-Company-Code` mismatch (`45420-45421`) | Alerts page ungated (P1-14) |
| HR admin | as above | as above | Role-string fallbacks are dead/wrong (P1-13) |
| Payroll-sensitive | Payroll module + permissions | Payslip reads scoped by company + employee (`70443-70471`, `80465-80493`) | Statutory debug chrome leaks a permission boolean (P2) |
| Talent-sensitive | — | — | **No surface exists** (P0-1) |
| ER-sensitive | — | — | **No surface exists** (P0-1) — ER confidentiality is proven only in smoke tests |
| Setup / admin | Operator session or allowlisted token | `WATHEFNI_SETUP_OPERATOR_CREDENTIALS`, superadmin context | No login rate limit (P0-3); tokens in `localStorage` (P1-20) |
| Internal / platform | `require_internal_access` | Single shared token | Cross-tenant capability (P0-5) |

Namespace isolation is explicitly enforced and fail-closed: employee tokens, legacy shared tokens, and browser
dashboard sessions are each rejected by name on `/dashboard/mobile/*` (`operator_mobile.py:1055-1070`). The
latent risk is the legacy shared-token + `X-HR-Phone` path (`app.py:44527+`, `45447-45457`), which is gated off
but would accept a client-supplied company if ever enabled.

---

## 10. EN / AR / RTL findings

| App | Catalog | EN keys | AR keys | Parity |
|---|---|---|---|---|
| Employee App | `src/i18n/{en,ar}.json` | 1300 | 1300 | Exact |
| HR co-bundle | `src/hr/i18n/{en,ar}.json` | 222 | 222 | Exact |
| HR Mobile | `src/i18n/{en,ar}.json` | 196 | 196 | Exact |
| HR Web | **no catalog** — inline `*Copy(locale)` helpers and `isAr` ternaries | n/a | n/a | Uneven |

- **HR Web has no i18n system.** Arabic exists as paired inline copy per component, with `dir={isAr ? 'rtl' : 'ltr'}` applied per workspace. A heuristic scan found ~246 user-visible English strings in non-test `.tsx` with no adjacent `isAr`/`Copy`/`t(`. Concentrations: `setup-console/SetupConsoleApp.tsx` (~44), `posthire/PostHire.tsx` (~35), `MigrationSyncShell.tsx` (~27), `Product2AuthoringPanel.tsx` (~25), `pages/ShellStates.tsx` (~22). **P1.**
- **Setup Console is effectively English-only.** An Arabic-speaking company administrator cannot configure the product in Arabic. **P1.**
- `main.tsx:41` — the crash shell ("Something interrupted the dashboard") is English-only. **P1** for an error screen a customer may actually see.
- Key-count parity on mobile does **not** prove journey coverage; it proves no missing keys. Clipping, truncation, line-breaking, numeral formatting and date direction remain unverified without a device (PH-11).
- Specific RTL defects: week-strip forced LTR (`ScheduleWeekStrip.tsx:187`), physical `left`/`right` badge under `swapLeftAndRightInRTL` (`HomeView.tsx:806-807`), decorative absolute positioning (`geometry.tsx:136-177`).

---

## 11. Setup Console findings

31 cards/sections inventoried; Wave 1, 2, 3, 4 and all 7 Wave 6 cards are mounted and reachable
(`SetupConsoleApp.tsx:74-81`, `866-920`).

1. **Wave 4 and Wave 6 cards configure capabilities that have no product** — P0-1. Setup is currently honest
   about policy and dishonest about capability.
2. **Wave 5 Intelligence has no card at all** — P1-1. The Wave 5 charter assigned Setup ownership; it was never built.
3. **Dual gating** — Setup toggle + `WATHEFNI_*_C#` flag + `WATHEFNI_*_COMPANIES` allowlist. Admin-visible state
   can say "enabled" while runtime fails closed, with no feedback in the card — P1-2.
4. **Duplicate policy ownership** — Leave, Attendance, Onboarding each configurable in two or three places — P1-18.
5. **Env-only settings** that a company cannot self-configure: `WATHEFNI_EMPLOYEE_APP` master flag,
   `WATHEFNI_PUSH_NOTIFICATIONS`, `WATHEFNI_ONBOARDING_SEED`, employee-app allowlists, channel presets,
   `notification_preset` (still only in a legacy HTML surface at `app.py:~42600-42653`) — P1.
6. **Positive**: company creation inserts only `companies` + `company_settings{timezone,currency}` — no demo
   employees, no fixture modules, no fake leave policies. Clean bootstrap is genuinely clean.
7. **Positive**: an explicit disable-semantics contract exists (stop new work, hide surfaces, block APIs,
   preserve history) — `setup_console_phase1_ownership.py:21-63`.

---

## 12. Infrastructure and security findings

| Area | State | Severity |
|---|---|---|
| Database migrations | **No migration framework.** Schema is `CREATE TABLE IF NOT EXISTS` (83 sites) + `ADD COLUMN IF NOT EXISTS` (153 sites) executed by `ensure_schema()` at runtime, plus ad-hoc `ops/migrate-*.py`. No versioning, no down-path, no drift detection | P1 |
| Backups | Real: `wathefni-backup.service` + `.timer`, `backup-wathefni.sh`, `RESTORE_RUNBOOK.md`, `restore-drill.sh`, `smoke-test-backup-restore.py` | PASS (drill recency unverified) |
| Rollback | Per-wave feature-flag rollback scripts; no single unified application rollback | P2 |
| Health / readiness | `/health` (`42142`) and `/ready` (`42155`) exist; `/health` leaks legacy-auth flag state | PASS / P2 |
| Error reporting | **None.** No Sentry/Rollbar/Bugsnag in orchestrator or any client. `AppErrorBoundary.componentDidCatch` is empty. A production crash is invisible unless a user reports it | P1 |
| Structured logging | Stdlib `logging` only; no JSON pipeline, no redaction layer. Phone numbers logged at `app.py:37538`, `68739` | P2 |
| CI / deploy gate | **No CI at all** (no `.github`). Qualification is manual script invocation | P1 |
| Job / queue failure handling | Strong for inbound email (durable ingress, dead-letter, `max_attempts`, replay); other workers vary | PASS / partial |
| Rate limiting | No global middleware; login surfaces unprotected | P0-3 |
| Secrets | No committed live credentials found; `.env` gitignored; client bundles carry only `EXPO_PUBLIC_*`. But two HMAC secrets fall back to committed constants | P0-2 |
| Storage / OCR / email / WhatsApp / push | Configured: local + Drive storage, Mistral OCR (flag-gated), Postmark, WhatsApp outbound, Expo push | PASS |
| Performance — N+1 | `app.py:64857-64858` (per-`app_key` SELECT, up to 1000), `13389-13437`, `8214-8218`, `41063-41064`; correlated subquery per leave row at `19100-19108` | P1 |
| Performance — unbounded | `company_employees()` (`14947-14966`) is intentionally uncapped `SELECT * FROM employees WHERE company_code=%s`; a capped `list_employees_page` exists but callers must opt in | P1 at scale |
| Performance — home fan-out | Employee `/app/home` = 1 HTTP but ≥7 module reads server-side (`69243-69341`); HR Mobile `build_mobile_priorities` (`operator_mobile_data.py:2384+`) sequentially fans out across leave, onboarding, preboarding, probation, requisitions, documents, swaps, tasks, rankings | P1 |
| Performance — sync heavy work | OCR on request path (`25937-25943`), in-process LLM calls (`6029+`, `6463`, `56791`), payslip PDF generated during download (`70491-70506`) | P1 |
| Performance — client | `apps/wathefni-hr-mobile` uses **no** `FlatList`/`FlashList`; employee leave/attendance history render via `.map` | P2 |

No performance measurements were taken. Every performance item above is a **code-shape risk**, not a measured
regression; R1 deliberately does not invent numbers.

---

## 13. Real-company readiness

**Can we stand up a clean named canary company today and operate it without developer intervention? No.**

| Requirement | Status |
|---|---|
| No fixture data at bootstrap | **Yes** — company creation inserts only `companies` + `company_settings` |
| Real configuration via Setup | **Partial** — Waves 1–3 yes; Wave 4/5/6 require environment edits (P1-1, P1-2), so a developer is required |
| Real employee | Yes — activation, PIN, biometric, ESS journey all implemented |
| Real documents | Yes — upload, OCR, compliance, review; but non-local docs hand out raw provider URLs (P1-21) |
| Real attendance / leave / payroll path | Yes on HR Web and Employee App; HR Mobile lacks a leave queue (P1-4) |
| Operate without developer intervention | **No** — env allowlists for Wave 4/5/6, no error reporting to notice failures (P1-23), no CI gate (P1-24) |
| Safe from accidental fixture injection | **No** — P0-6 |

Per the charter, the canary is not attempted while P0s are open.

---

## 14. Recommended R2–Rn execution order

Ordered by "what makes the next phase possible", not by finding count. Each phase stops for owner review.

**R2 — Security and secret hardening** (P0-2, P0-3, P0-4, P0-5, P1-22)
Fail-closed link secrets; rate limiting and lockout on both login surfaces plus a global middleware; remove the
localhost fail-open; tenant-scope or formally break-glass the internal audit/debug/intake endpoints with operator
attribution and audit logging. Small, self-contained, and it unblocks any live probing later. Re-prove with a
negative-path test suite.

**R3 — Production data safety** (P0-6, plus the `"WATHEFNI"` default-company fallback)
Make every `ops/ops-seed-*` and matrix script refuse to run unless an explicit non-production target is asserted;
remove `setdefault(WATHEFNI_ENV, production)`; require an interactive confirmation for destructive statements.
Cheap, and it removes the risk of corrupting the very tenant R5 will create.

**R4 — Truth-in-UI** (P0-7, P1-12, P1-10, P1-11, P1-13, P1-14, P1-16, P1-17)
Error states must be errors: thread `isError` through Interviews and the Overview work queue, remove silent
catches that manufacture empty lists, wire `showWorkQueue`/`showRolePriority`, delete the null delivery
components and the "not implemented" control, fix the wrong role strings, gate the Alerts page, centralise
notification suppression for disabled modules, fix the `migration-sync` deep link.

**R5 — Wave 4 / Wave 6 surface decision** (P0-1) — *the largest phase, and an owner decision first*
Two honest paths, and the owner must choose before engineering starts:
  (a) **Hide** — remove the Wave 4 and Wave 6 cards from Setup until surfaces exist. Restores honesty in days;
      the HCM expansion stays a backend asset.
  (b) **Ship** — build HTTP APIs + HR Web pages (+ the thin HR Mobile and Employee App surfaces each module's
      charter specified) for all eight domains. This is a multi-wave programme, not a fix.
A hybrid is likely correct: hide everything now, then ship modules one at a time behind the existing gates.

**R6 — Setup self-service completeness** (P1-1, P1-2, P1-3, P1-5 env-only items, P1-18)
Build the Wave 5 Intelligence card; collapse the Setup-toggle-plus-env-allowlist dual gate into a single visible
state (or surface the runtime gate in the card so "enabled" never lies); resolve duplicate policy ownership.

**R7 — Mobile keyboard and native safety** (PH-1 … PH-4, P1-6, P1-7, P1-8, P1-9, P1-4, P1-5)
Introduce one shared keyboard-safe screen primitive across both mobile apps, including Android behaviour; remove
hardcoded offsets; then fix the dead affordances, the missing HR Mobile leave queue and task actions, and the
orphaned employee preboarding/probation screens.

**R8 — Observability and delivery** (P1-23, P1-24, migrations)
Error reporting on all four surfaces, structured logging with redaction, CI running the existing wave
qualification suites, and a real migration framework with versioning and drift detection.

**R9 — Live permission and tenant-isolation probing**
What R1 could not do: authenticate as each role and probe direct URLs and API endpoints, including cross-tenant
IDs, on a two-tenant staging environment. Add the missing `company_code` predicates found in P1-19 as
defence-in-depth.

**R10 — Performance measurement**
Measure before optimising: instrument the employee Home, HR Web bootstrap and HR Mobile priorities; load a tenant
with realistic headcount; then fix the N+1s, the uncapped `company_employees`, and the synchronous OCR/PDF/LLM
work with evidence.

**R11 — EN/AR/RTL completion** (§10)
Give HR Web a real i18n layer, translate the Setup Console, then walk full journeys in Arabic.

**RP — Physical device qualification** (§5)
Real iOS and Android hardware, EN and AR, all 11 matrix items observed and recorded.

**RC — Clean canary company**
Only after R2–R8 and RP. One real named company, zero fixture data, no developer intervention.

---

## 15. Audit limits — what R1 did not prove

Stated explicitly so nothing here is mistaken for verified:

- No code was executed. No staging or production request was issued. No database was queried.
- Permissions were read, not probed. Direct-URL and direct-API bypass testing is deferred to R9.
- Module composition was assessed from composition code, not by provisioning tenants with 1, 2, and N modules.
- No performance number was measured; all performance findings are code-shape risks.
- No physical device was used; all 11 PHYSICAL items remain unproven.
- Cross-surface convergence was traced through code paths, not by mutating a record and observing three clients.
- Runtime environment values (which flags and secrets are actually set in production) were not inspected;
  findings that depend on them are written as "fails open if unset", which is the correct posture regardless.

---

## 16. Marker

Audit completed honestly, with defects reported as found and no finding suppressed to produce a pass.

**PRODUCTION_READINESS_R1_AUDIT_COMPLETE**

Product is **not** stamped ready. Nothing was fixed. Stopping for owner review to confirm the R2–Rn sequence and,
in particular, to decide the Wave 4 / Wave 6 surface question in R5.
