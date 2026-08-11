# Employee Mobile — Rolling Canary Qualification Log

**Canary employees:** Aziz `WATHEFNI-96599338566` · Talal `WATHEFNI-96550252254`  
**Process:** `ops/EMPLOYEE_MOBILE_CONTINUOUS_WAVE_PROCESS.md`  
**Rule:** `.cursor/rules/employee-mobile-continuous-waves.mdc`

Append one row (or section) per internal ship. Do not wait for owner review between rows.

---




## 20260811T103500Z — HR Settings live session/queue probe + pagination blockers logged

| Field | Value |
| --- | --- |
| Scope | (1) Logged pagination must-fix #1–#3 in `ops/HR_MOBILE_QUEUE_PAGINATION_PRE_CUSTOMER_BLOCKERS.md` for post-visual pre-customer hardening. (2) HR Settings **Session · queues** live probe: API base, operator session, OTA id, raw→rendered→VISQA counts for Docs/Tasks/Alerts/Onboarding/Attendance Today — no demo data, invalidates query cache after probe. |
| Ship | OTA **`75042c41-ca1b-4e10-8306-dd16c84c256c`** · runtime 0.3.0 · canary · iOS `019ff064-98f1-7603-a453-9dd58148e559` |
| Verdict | Visual wave paused until on-device probe shows VISQA>0; client pipeline vs Aziz prod does not drop VisQA |

---

## 20260811T102600Z — HR Onboarding Editorial Entity Detail (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Onboarding detail visual — yellow ambient accent, employee identity + Needs HR lead, work items with Accept/Waive pills, waiting-on-employee as quiet typography, ConfirmationSheet outside scroll. Accept/Waive/bank/preview contracts unchanged. |
| Ship | OTA **`3985e5ff-5d35-4de1-8bb5-9edc7a9a3601`** · runtime 0.3.0 · canary · iOS `019ff05c-3328-712b-895e-5864bf4f8228` |
| Verify | `verify-hr-onboarding-review.py` GREEN |
| Verdict | **Shipped canary** — next Editorial Entity Detail candidates: Attendance exception / Shift swap |

---

## 20260811T100100Z — HR mobile VisQA synthetic fixtures seeded (production)

| Field | Value |
| --- | --- |
| Scope | Disposable VisQA fixtures for Document Reviews, Onboarding, HR Tasks, Delivery Alerts, Attendance, Shift swaps — marker `hr_mobile_visqa_v1` |
| Employees | Sara `WATHEFNI-9655280101` · Fahad `WATHEFNI-9655238102` · Noura `WATHEFNI-9655248103` (never Aziz/Talal) |
| Tool | `ops/mobile-e2e/provision-hr-visqa-fixtures.py` · docs `ops/mobile-e2e/VISQA_FIXTURES.md` |
| Verify | mobile API: docs VisQA=4 · onboarding=1 · tasks≥2 · alerts=3 · attendance today=1 unresolved=3 · swap=1 · Civil ID detail 200 |
| Cleanup | `python3 ops/mobile-e2e/provision-hr-visqa-fixtures.py --cleanup` |
| Verdict | **Ready for owner visual review** of populated detail states |

---

## 20260811T093900Z — HR Tasks Editorial Entity Detail (canary OTA)

| Field | Value |
| --- | --- |
| Scope | HR Task detail visual — yellow accent, employee·type lead, body as prose, unboxed About facts, pink attention only for high priority, ink Mark done pill. expected_status / no dismiss-assign preserved. Bundles Document Review visual. |
| Ship | OTA **`ad637b8d-805f-4efd-94ce-a79b9752b268`** · runtime 0.3.0 · canary · iOS `019ff031-f003-747c-92a9-a89114089ae3` |
| Verify | `verify-hr-tasks-follow-ups.py` GREEN · `verify-hr-documents-reviews.py` GREEN |
| Verdict | **Shipped canary** for owner visual judgment on Document + Task details |

---

## 20260811T093700Z — HR Document Review Editorial Entity Detail (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Document Review detail visual — olive accent, expiry lead, unboxed Record facts, File actions, ink Mark reviewed pill, pink attention only when expired/missing/≤14d. Contracts preserved. |
| Ship | OTA **`13d6a012-dc53-4448-9bbd-be723c07d1b3`** · runtime 0.3.0 · canary · iOS `019ff030-b71d-7597-a60b-30eae43cb14b` |
| Verify | `verify-hr-documents-reviews.py` GREEN |
| Verdict | **Shipped canary** — Tasks visual follow-up OTA next |

---

## 20260811T093230Z — HR Employee Profile Editorial Entity Detail visual prototype (canary OTA · owner visual judge)

| Field | Value |
| --- | --- |
| Scope | Employee Profile visual-only prototype — cream + ink, one powder-blue accent dot, filled Wathefni status chips, role·dept lead, Contact + Tenure groups, no boxed facts. Frozen facts/RBAC/states unchanged. |
| Ship | OTA **`be3a329c-47fd-41ad-b426-7fa600220130`** · runtime 0.3.0 · canary · iOS `019ff02a-92b0-7915-9a21-3e41ae7c5c4b` |
| Verify | `verify-hr-employee-profile.py` GREEN · `physical-hr-employee-profile-en-ar.py` PASS |
| Contract | Facts-only freeze intact — no E360 / module hub / mutations / manager invent |
| Verdict | **Shipped canary for owner live visual judgment** — do not roll Editorial Entity Detail to other details until accepted |
| Next | Owner open People → employee profile on canary build; accept/reject visual; then roll language or iterate |

---

## 20260811T054700Z — BrowserStack Maestro real-device gate online (launch smoke MOBILE_PASS)

| Field | Value |
| --- | --- |
| Scope | BrowserStack App Automate + Maestro wired into `ops/mobile-e2e`; RC IPA `0.3.0` build 23 uploaded |
| Device | **Real iPhone 15 (iOS 17.5)** via BrowserStack — not simulator |
| RC | EAS `fa70005b-…` · `bs://41149d60ef1f119af901722322179a92ed2c0b67` · channel canary |
| MOBILE_PASS | **1** — launch + principal chooser visible (`00-launch-unsigned`) |
| FAIL | Continue-as-employee / Continue-as-HR taps do not navigate (XCTest `clickable=null`) — HR login / Leave Confirm not yet MOBILE_PASS |
| Face ID | **DEBT** — not automatable as PASS on BS without dedicated biometric capability proof |
| Evidence | `ops/evidence/mobile-e2e-bs-20260811T054531Z/` · dashboard `…/builds/5e7ac74aa09b9363ff7182185d3cb9310ccee1f1` |
| Verdict | **Launch smoke SHIP (canary-only)** · **Broad HR+Employee NO-SHIP** until auth/tabs/Leave Confirm pass on device |
| Next | Owner: HR email/password + requested `leave_id`; decide canary OTA to remove stuck chooser / restore pressables; then expand matrix |

---

## 20260810T210000Z — Permanent Maestro mobile E2E harness scaffolded (MOBILE_PASS still 0)

| Field | Value |
| --- | --- |
| Scope | Permanent release harness: Maestro smoke flows + `ops/mobile-e2e` gate + `e2e.*` testIDs + API reconcile |
| Device | **BLOCKED** — iOS Simulator runtime missing; disk free ~1 GB (needs ≥9 GB for runtime); no adb/USB Android |
| Device cloud | None (BrowserStack/Sauce/Maestro Cloud **not** added — local sim/USB is first path) |
| Harness | `ops/mobile-e2e/README.md` · `run-release-gate.py` · `.maestro/smoke/*` · `verify-mobile-e2e-testids.py` |
| Rule | Gate refuses to invent `MOBILE_PASS` when `ui_runtime_ready=false` |
| Evidence | `ops/evidence/mobile-e2e-gate-20260810T200700Z/` |
| Verdict | Infrastructure progress only — **HR NO-SHIP** · **Employee NO-SHIP** until a real sim/device runs smoke |
| Next | Free disk → download iOS runtime → install RC on sim → re-run `python3 ops/mobile-e2e/run-release-gate.py` |

---

## 20260810T194000Z — Full HR + Employee mobile E2E product qualification (NO-SHIP)

| Field | Value |
| --- | --- |
| Scope | Full end-to-end product matrix: routes, modules, RBAC/tenant, mutations, cross-surface, auth — **API PASS ≠ MOBILE PASS** |
| Device | **BLOCKED** — no iOS simulator / USB / adb on qual host → **MOBILE_PASS = 0** |
| API_SPINE | WATHEFNI priorities↔queues aligned; Leave/Onboarding/Docs/Tasks mutations→DB; CV auth bytes; cross-tenant leave denied; Talal workday/leave/payslips/docs/onboarding/notifications; bank ESS fail-closed 403 |
| Multi-tenant | BOOTPRE01/BOOTPOST01/BOOTMIX01 / TENANTISO* **absent** on prod (`company_modules` companies = 2) — module-off UI matrix incomplete |
| Static | 32 PASS · harness/style DEBT (deep-nav string, documents back string, color/density/RTL) — not product FAIL after reclassification |
| Product FAIL | **0** this run (schedule was wrong path `/app/schedule` vs `/app/workday`) |
| Evidence | `ops/evidence/full-mobile-e2e-qual-20260810T194000Z/` · canvas `full-mobile-e2e-product-qual.canvas.tsx` |
| Verdict | **HR NO-SHIP** · **Employee NO-SHIP** — canary OTA continued use OK; broad release blocked until owner-device MOBILE_PASS matrix |
| Next | Owner device: Leave Confirm smoke · full Confirm/file/auth/EN·AR·RTL matrix; optional BOOT* module tenants for module-off proof |

---

## 20260810T185200Z — Three release blockers (Leave Confirm · Onboarding queue · Docs queue)

| Field | Value |
| --- | --- |
| Scope | Leave Confirm silent-fail; onboarding HR-actionable SQL queue; compliance needs_review projection truth |
| Leave | ConfirmationSheet outside ScrollView; inline error; non-blocking post-success refresh; verify-hr-leave-detail GREEN |
| Onboarding | `list_onboarding_hr_actionable_page` — mobile/Home/Inbox share actionable set (no ~90 in_progress scan) |
| Documents | SELECT `renewal_status`; `pending_hr_review`→`needs_review`; valid-without-renewal not flooded into queue |
| Ship | Backend prod restart · OTA **`7c52c216-8534-4e16-a141-ab177495dea5`** (iOS `019fed03-…`) |
| Evidence | `ops/evidence/hr-three-blocker-fix-20260810T185200Z/` |
| Verdict | Onboarding **PASS** · Documents **PASS** · Leave **PASS (fix+HTTP)** with owner Confirm smoke on OTA |
| Next | Owner Confirm smoke on seeded Fouad leaves; then Face ID/auth physical QA |

---

## 20260810T183500Z — HR Confirmation / File / Auth physical canary (CONDITIONAL · API spine)

| Field | Value |
| --- | --- |
| Scope | Live prepare→confirm + authenticated file bytes + auth matrix as Aziz; no frozen UX reopen |
| Device | **BLOCKED** — no iOS simulator/USB on build host (Face ID / auto-lock / Forgot PIN / UI safe-back / locale) |
| PASS | Attendance prepare→confirm · Shift swap reject confirm · Onboarding Accept/Waive confirm · Document mark reviewed mutation · HR Task mark done · Onboarding/Doc/CV file allowlist + auth GET 200 |
| Blockers | (1) Onboarding list scans only first ~90 `in_progress` → queue empty while `being_reviewed` exists; (2) Compliance payload status `missing` vs table `needs_review` → Document Reviews queue empty |
| Hygiene | Attendance verifier Wordmark → cream `PageScreen + EditorialHeading` |
| Evidence | `ops/evidence/hr-confirm-file-auth-physical-20260810T181835Z/` (+ static `…-matrix-20260810T181353Z/`) |
| Verdict | **CONDITIONAL** — confirmation/file spines proven; queue discoverability + device auth still open |
| Next | Owner-device auth/UI pass; fix onboarding pagination + compliance queue status alignment (separate from freezes) |

---

## 20260810T181353Z — HR Confirmation / File / Auth matrix (CONDITIONAL · physical pending)

| Field | Value |
| --- | --- |
| Scope | Cross-cutting matrix after Employee Profile freeze: ConfirmationSheet hosts, `openAuthenticatedFile`, HR local-lock |
| Profile | Already **PASS/FROZEN** (`20260810T180148Z` · OTA `66eab204-…`) — not reopened |
| Static | Leave/Candidate confirm stamped; Attendance/Swap/Onboarding SOD hooks wired; Docs/Tasks client sheet + `expected_status`; file path allowlist; local-lock + settings verifies GREEN |
| Physical pending | Decision prepare→confirm on Attendance/Swap/Onboarding/Docs/Tasks; authenticated file open; Face ID/auto-lock/Forgot PIN |
| Debt note | `verify-hr-attendance-exceptions` Wordmark FAIL (script/chrome hygiene) — fixed in `20260810T183500Z` |
| Evidence | `ops/evidence/hr-confirm-file-auth-matrix-20260810T181353Z/` |
| Verdict | **CONDITIONAL** — superseded by physical stamp `20260810T183500Z` |
| Next | Physical confirmation + file + auth canary; then stamp PASS (no product freeze for this cross-cut) |

---

## 20260810T180148Z — HR Employee Profile cream honesty (PASS · canary OTA · FROZEN)

| Field | Value |
| --- | --- |
| Scope | `/hr/employees/[employeeKey]` cream facts-only; drop manager_name; localized status; unavailable/not-found; no E360 |
| Backend | Unchanged quick profile DTO (no manager); spine reconfirmed |
| Ship | OTA **`66eab204-7f74-441b-8df2-b54a8ec8cf45`** · runtime 0.3.0 · canary · iOS `019fecd7-a208-74cf-aced-c3157b14d130` |
| Gates | verify-hr-employee-profile · physical-hr-employee-profile-en-ar · people-directory · tsc · spine-probe |
| Evidence | `ops/evidence/hr-employee-profile-cream-20260810T180148Z/` |
| Freeze | `.cursor/rules/hr-mobile-employee-profile-freeze.mdc` · debt `ops/HR_MOBILE_EMPLOYEE_PROFILE_CONTRACT_DEBT.md` |
| Verdict | **PASS** (canary · FROZEN) |
| Next | Remaining confirmation / file / auth qualification matrix |

---

## 20260810T175300Z — HR Employee Profile detail qualification (CONDITIONAL · not locked)

| Field | Value |
| --- | --- |
| Scope | `/hr/employees/[employeeKey]` audit (Aziz); People→canonical profile; no redesign |
| Live | Directory 112; quick profile strips E360 sections; **no manager_name**; missing→404; facts email/phone/start real |
| Honesty | Manager UI claimed but API silent; empty-key ready blank; raw employment_status |
| Role | Facts-only quick profile v1 intentional; restrained module links deferred; not E360 |
| Visual | People cream; profile still `@hr/theme` OperationalDetailView |
| Evidence | `ops/evidence/hr-employee-profile-qual-20260810T175300Z/` |
| Verdict | **CONDITIONAL** — freeze after one cream+honesty patch (not E360) |
| Next | Contained patch: cream + drop/flag manager + not-found/empty → physical EN/AR → freeze |

---

## 20260810T174850Z — HR Hiring + Candidates list + Interviews cream honesty (PASS · canary OTA · FROZEN)

| Field | Value |
| --- | --- |
| Scope | Hiring home honesty + cream Candidates/Interviews/Jobs; position-scoped ranking; notes concurrency tokens; Assistant `interview_id`; Assessments hidden; EN/AR priority/upcoming |
| Backend | Priorities → `/jobs` or `/candidates?position=`; `notes_version` on interview DTO; notes `expected_*` wired; backup `/opt/wathefni/backups/hr-hiring-interviews-20260810T174850Z` |
| Ship | OTA **`56af1a85-d1b3-494d-957f-2f9668b93ac1`** · runtime 0.3.0 · canary · iOS `019feccc-30a3-7fa6-958a-a733106dea71` |
| Gates | verify-hr-hiring-home · verify-hr-hiring-interviews-wave · physical-hr-hiring-interviews-en-ar · verify-hr-mobile-assistant · tsc · spine-probe |
| Evidence | `ops/evidence/hr-hiring-interviews-cream-20260810T174850Z/` |
| Freeze | `.cursor/rules/hr-mobile-hiring-interviews-freeze.mdc` · debt `ops/HR_MOBILE_HIRING_INTERVIEWS_CONTRACT_DEBT.md` |
| Verdict | **PASS** (canary · FROZEN) |
| Next | Continue adjacent HR mobile waves under continuous canary; do not expand Assessments / schedule mutations without owner wave |

---

## 20260810T173000Z — HR Hiring Home + Interviews qualification (CONDITIONAL · not locked)

| Field | Value |
| --- | --- |
| Scope | `/hr/hiring` + `/hr/candidates` list + `/hr/interviews` list/detail audit (Aziz); no redesign |
| Live | Prehire priorities present; `candidate_decisions` empty (unscoped rankings); interviews=4; notes without token → `missing_expected_version`; Assistant app_key-as-interviewId fails |
| Blockers | Notes concurrency tokens missing · Candidates fake empty (flags dropped) · Assistant interview id kind wrong |
| Honesty | Jobs/Assessments→Candidates remap weak · priority→unscoped list · upcoming EN hardcodes · schedule_interview→list only |
| Visual | Hiring cream OK; Candidates/Interviews lists+detail still `@hr/theme` legacy |
| Evidence | `ops/evidence/hr-hiring-interviews-qual-20260810T173000Z/` |
| Verdict | **CONDITIONAL** — freeze Hiring + Interviews **together** after honesty + cream-list wave |
| Next | Patch blockers (position-scoped Candidates, notes tokens, Assistant id) + cream lists → physical EN/AR → dual freeze |

---

## 20260810T172200Z — HR Candidate detail cream + honesty (PASS · canary OTA · FROZEN)

| Field | Value |
| --- | --- |
| Scope | `/hr/candidates/[appKey]` cream + honesty: stage tone, no `#appKey`, CV empty EN/AR, localized confirm/consequence, `already_decided`, offer.current when present; rankings honesty (`requires_position`) without parallel list |
| Backend | `mobile_candidate_rankings` surfaces `job_required` honestly; backup `/opt/wathefni/backups/hr-candidate-rankings-honesty-20260810T172200Z` |
| Ship | OTA **`1eb84033-38da-4772-8397-4d31c5cb2793`** · runtime 0.3.0 · canary · iOS `019fecb6-43fd-72f7-906e-34d115825bd7` |
| Gates | verify-hr-candidate-detail · physical-hr-candidate-en-ar · nav-ergonomics · deep-nav · tsc · spine-probe |
| Evidence | `ops/evidence/hr-candidate-detail-cream-20260810T172200Z/` |
| Freeze | `.cursor/rules/hr-mobile-candidate-freeze.mdc` · debt `ops/HR_MOBILE_CANDIDATE_CONTRACT_DEBT.md` |
| Verdict | **PASS** (canary · FROZEN) |
| Next | Hiring home / Interviews physical-surface qualification |

---

## 20260810T171500Z — HR Candidate detail qualification (CONDITIONAL · not locked)

| Field | Value |
| --- | --- |
| Scope | `/hr/candidates/[appKey]` audit + production helper exercise (Aziz); import ready_for_review prepare shortlist (no confirm); terminal archived read |
| Backend | Prepare SOD works; detail + CV real; rankings list 0 items (queue discovery debt); offer key present unused by UI |
| Client gaps | Legacy plum card stack · always-info badge · `#appKey` chrome · EN-only CV/consequence · `already_decided` unwired · offer not rendered |
| Evidence | `ops/evidence/hr-candidate-detail-qual-20260810T171500Z/` |
| Verdict | **CONDITIONAL** — do not lock Candidate until cream + honesty (Leave pattern) |
| Next | Patch Candidate honesty + cream → physical EN/AR → freeze |

---

## 20260810T170800Z — HR Leave detail cream + honesty (PASS · canary OTA · FROZEN)

| Field | Value |
| --- | --- |
| Scope | `/hr/leave/[id]` honesty + cream migration: real balances + observe-only caption; EN/AR conflict/confirm/consequence; `already_decided`; status tone from real status; `HrPushedNav` cream surface; no plum stack / `#id` chrome |
| Backend | Unchanged SOD prepare→confirm; spine reconfirmed (Fouad balance 17.5 observe-only; disposable Talal approve) |
| Ship | OTA **`21e2ccc7-eb8e-414b-9b0e-ab1161699aef`** · runtime 0.3.0 · canary · iOS `019feca4-d4a8-7a5e-a48c-642b66a38943` |
| Gates | verify-hr-leave-detail · physical-hr-leave-en-ar · tsc · spine-reenforcement |
| Evidence | `ops/evidence/hr-leave-detail-cream-20260810T170800Z/` |
| Freeze | `.cursor/rules/hr-mobile-leave-freeze.mdc` · debt `ops/HR_MOBILE_LEAVE_CONTRACT_DEBT.md` |
| Verdict | **PASS** (canary · FROZEN) |
| Next | Candidate detail physical-surface qualification |

---

## 20260810T165300Z — HR Leave detail qualification (CONDITIONAL · not locked)

| Field | Value |
| --- | --- |
| Scope | `/hr/leave/[id]` audit + production helper exercise (Aziz); disposable Talal approve; Fouad conflict/balance read |
| Backend | Prepare/confirm SOD works; conflict count matches DB; balance payload real; priorities drop decided item |
| Client gaps | Fake balance card · EN-only conflict/consequence · confirm action raw verb · `already_decided` unwired · always-attention badge |
| Visual | Legacy `@hr/theme` vs cream HR — exact change list in evidence (no redesign shipped) |
| Evidence | `ops/evidence/hr-leave-detail-qual-20260810T165300Z/` |
| Verdict | **CONDITIONAL** — do not lock Leave until honesty fixes + one physical EN/AR pass |
| Next | Fix Leave honesty → physical stamp → Candidate detail |

---

## 20260810T163253Z — HR Assistant Thinking + real stream paint (PASS · canary OTA + API)

| Field | Value |
| --- | --- |
| Scope | Quiet **Thinking** / **يفكر** instead of cheap `…` bubble; `expo/fetch` SSE body streaming; client delta reveal fallback; paced 2-word server chunks; assistant reply as plain text |
| Backend | `operator_mobile_assistant.py` paced deltas + no-buffer headers; backup `/opt/wathefni/backups/hr-assistant-thinking-20260810T163253Z` |
| Ship | OTA **`ac513bb4-2e70-491d-b0be-f27d1dfc5628`** · runtime 0.3.0 · canary · iOS `019fec86-1ab6-7bed-91e8-e0252e3d07db` |
| Gates | verify-hr-mobile-assistant · test_hr_mobile_assistant · tsc · health 200 |
| Evidence | `ops/evidence/hr-assistant-thinking-stream-20260810T163253Z/` |
| Rollback | OTA prior `4dd457d0-…` |
| Verdict | **PASS** (canary) |

---

## 20260810T162614Z — HR Assistant stream + composer/logo/scroll (PASS · canary OTA + API)

| Field | Value |
| --- | --- |
| Scope | Chunked reply SSE deltas (same final text); logo badge mark; FlatList always-scroll + interactive keyboard dismiss; composer padding/height/keyboard gap fix; pink send unchanged |
| Backend | `operator_mobile_assistant.py` chunked deltas; backup `/opt/wathefni/backups/hr-assistant-stream-20260810T162614Z` |
| Ship | OTA **`4dd457d0-dbb7-4d1a-8ff8-af60a05628e9`** · runtime 0.3.0 · canary · iOS `019fec7f-f55e-7e91-a9e7-7a4aa15a27d5` |
| Gates | verify-hr-mobile-assistant · test_hr_mobile_assistant · tsc · health 200 |
| Evidence | `/Users/azizalmulla/Desktop/claw/ops/evidence/hr-assistant-stream-composer-20260810T162614Z/` |
| Verdict | **PASS** (canary) |

---

## 20260810T160220Z — HR Assistant calm empty state (PASS · canary OTA)

| Field | Value |
| --- | --- |
| Scope | Remove suggestion chips + Update chips; empty = compact Wordmark + Kuwait-local greeting by display name; no Assistant hero; conversation drops empty land; pink send when sendable / quiet when empty; floating composer + keyboard unchanged; spine/backend unchanged |
| Backend | None (JS/OTA only) |
| Ship | OTA **`d91a32b9-f5eb-4d42-836c-b2364388cefb`** · runtime 0.3.0 · canary · iOS `019fec69-e7c9-7382-83dd-9ebb009719af` |
| Gates | verify-hr-mobile-assistant · tsc |
| Evidence | `/Users/azizalmulla/Desktop/claw/ops/evidence/hr-assistant-empty-calm-20260810T160220Z/` |
| Verdict | **PASS** (canary) |

---

## 20260810T155350Z — HR Home refresh + People profile path (PASS · canary OTA)

| Field | Value |
| --- | --- |
| Scope | Home pull-to-refresh spinner only during user pull (not `isFetching`/focus refetch); People row always `/hr/employees/{key}`; onboarding chip separately opens `/hr/onboarding/{key}` when permitted; Home/Inbox onboarding priorities unchanged |
| Backend | None (JS/OTA only) |
| Ship | OTA **`e5d788d9-e3ed-4deb-a842-2470da27336e`** · runtime 0.3.0 · canary · iOS `019fec62-1cd3-795f-adb0-4ba3f6d46acd` |
| Gates | verify-hr-home-parity · verify-hr-people-directory · tsc |
| Evidence | `/Users/azizalmulla/Desktop/claw/ops/evidence/hr-home-people-nav-fix-20260810T155350Z/` |
| Verdict | **PASS** (canary) |

---

## 20260810T155041Z — HR Mobile Assistant chat UX polish (PASS · canary OTA)

| Field | Value |
| --- | --- |
| Scope | Compact wrapping suggestion chips; circular black ↑ send; floating rounded composer; auto-grow input; keyboard + safe-area avoidance; quieter refresh; cream/black with restrained brand accents; EN/AR/RTL preserved |
| Backend | None (JS/OTA only — no AI/spine behavior change) |
| Ship | OTA **`8f83e776-63c8-445d-a16b-056370b2734a`** · runtime 0.3.0 · canary · iOS `019fec5f-620e-7773-b3e7-de87786819e8` |
| Gates | verify-hr-mobile-assistant · tsc |
| Evidence | `/Users/azizalmulla/Desktop/claw/ops/evidence/hr-mobile-assistant-chat-ux-20260810T155041Z/` |
| Verdict | **PASS** (canary); physical keyboard/empty/long/stream matrix on device |

---

## 20260810T153357Z — HR Mobile Assistant V1 (PASS · canary OTA + API)

| Field | Value |
| --- | --- |
| Scope | Thin mobile client of Wathefni Assistant spine under More; cream/black chat; EN/AR/RTL; stream; dynamic chips; safe deep links via `destinationAvailable`; conservative confirm; no ai-recruiter; channel `hr_mobile` |
| Backend | `operator_mobile_assistant.py` + `operator_mobile.py` assistant feature/routes; backup `/opt/wathefni/backups/hr-mobile-assistant-20260810T153357Z`; health 200 on `:8010` |
| Ship | OTA **`1baaf28a-7966-4221-a13f-bf5c7ff793d2`** · runtime 0.3.0 · canary · iOS `019fec52-60e1-7d65-97da-aa3ab8323ad6` |
| Gates | verify-hr-mobile-assistant · verify-hr-more-launcher · verify-hr-navigation-ergonomics · test_hr_mobile_assistant · tsc |
| Evidence | `/Users/azizalmulla/Desktop/claw/ops/evidence/hr-mobile-assistant-20260810T153357Z/` · demo prompts (no fake data) in `DEMO_PROMPTS.md` |
| Not in scope | Widening frozen module authority for chat · SMS/Telegram/Teams/push send · separate AI backend · P0–P2 Setup→AI parity full prod promote (still local; mobile uses existing prod spine) |
| Verdict | **PASS** (canary); physical device pull + live prompt matrix remaining |

---

## 20260810T093000Z — Employee navigation ergonomics E1–E7 (PASS · canary OTA)

| Field | Value |
| --- | --- |
| Scope | Shared `useEmployeeSafeBack` + `employeeCanonicalParent`; wire all pushed routes; loading/error/unavailable keep Back; Bank unavailable safe fallback; Change PIN never blank → Settings; Payslip Android `BackHandler`; signed-out auth-only Stack |
| Backend | None (JS/OTA only) |
| Not in scope | D1–D4 debt · cream redesign · Home tab navigate |
| Ship | OTA **`baecb510-3fa4-4af7-a13c-ce288f4103d0`** · runtime 0.3.0 · canary · iOS `019feb06-3558-7546-914e-c4c07666fbf1` |
| Gates | verify-employee-navigation-ergonomics · verify-hr-navigation-ergonomics · tsc |
| Debt | `ops/EMPLOYEE_MOBILE_NAV_ERGONOMICS_DEBT.md` |
| Verdict | **PASS** (E1–E7 green; D1–D4 debt) |

### E1–E7

| Item | Verdict |
| --- | --- |
| E1 Shared safe-back | **PASS** |
| E2 Bare back on pushed routes | **PASS** |
| E3 Loading/error escape chrome | **PASS** |
| E4 Bank unavailable | **PASS** |
| E5 Change PIN blank/safe return | **PASS** |
| E6 Payslip hardware back | **PASS** |
| E7 Signed-out auth-only stack | **PASS** |

---

## 20260810T090500Z — HR navigation ergonomics B1–B4 (PASS · canary OTA)

| Field | Value |
| --- | --- |
| Scope | Shared safe-back contract (`canGoBack` → back else replace canonical parent); visible Back on all pushed/detail HR screens; module/hiring lists as pushed; tab roots unchanged; signed-out auth-only Stack (no swipe into authenticated shells); RTL back icon preserved |
| Backend | None (JS/OTA only) |
| Not in scope | Cream redesign · Home tab `navigate` · retiring `/hr/employees` duplicate |
| Ship | OTA **`8ef75b0c-6a6c-4faa-bf9d-a0c4eaeb385f`** · runtime 0.3.0 · canary · iOS `019feaec-b3ac-7c77-a863-4787ccdeabe4` |
| Gates | verify-hr-navigation-ergonomics · verify-hr-deep-nav-blockers · verify-hr-delivery-alerts-monitor · tsc |
| Debt | `ops/HR_MOBILE_NAV_ERGONOMICS_DEBT.md` |
| Next | Physical canary swipe/system-back matrix; remaining debt below |
| Verdict | **PASS** (B1–B4 green) |

### Classification

| Item | Verdict |
| --- | --- |
| B1 Legacy detail Back | **PASS** |
| B2 Pushed module/hiring list Back | **PASS** |
| B3 Safe-back helper / cold-start fallback | **PASS** |
| B4 Signed-out auth-only stack | **PASS** |
| Home push Inbox/More · cream/legacy chrome split · People duplicate | **SAFE POST-LAUNCH DEBT** |

---

## 20260810T084500Z — HR deep-nav / principal isolation blockers (PASS · canary OTA + API)

| Field | Value |
| --- | --- |
| Scope | Release-blocker remediation: Employee shell hard-denies `/hr/*` (no Stack mount, sync Redirect); remap `/ranking` + filtered `/candidates?…` → `/candidates`; Hiring + Delivery Alerts `destinationAvailable`; Leave/Candidate mobile APIs fail-closed via `_require_mobile_feature_action` |
| Backend | Deployed `operator_mobile_data.py`; backup `/opt/wathefni/backups/hr-deep-nav-blockers-20260810T084354Z`; health 200 on `:8010` |
| Not in scope | Cream/black nested-screen redesign · implementing mobile candidate list filters · dedicated `/ranking` surface |
| Ship | OTA **`01bb1c82-72e2-421e-80b0-8827abb72992`** · runtime 0.3.0 · canary · iOS `019fead8-adc4-7319-bbc8-5dac2a6d1f66` |
| Gates | verify-hr-deep-nav-blockers · verify-hr-hiring-home · verify-hr-shell-postauth-crash · verify-hr-delivery-alerts-monitor · tsc |
| Debt | `ops/HR_MOBILE_DEEP_NAV_BLOCKERS_DEBT.md` |
| Next | Final pre-release qualification matrix below; cream migration only if leftover nested screens hurt today’s release quality |
| Verdict | **PASS** (correctness blockers green; visuals deferred) |

### Blocker + pre-release verdicts

| Check | Verdict |
| --- | --- |
| Hard-deny `/hr/*` from Employee principal/shell | **PASS** |
| Dead `/ranking` + misleading candidate query deep links | **PASS** (stop-emitting) |
| Hiring destination validation (parity with Home/Inbox) | **PASS** |
| Deep-link module/permission/principal fail-closed (static + route gates + API feature actions) | **PASS** |
| Leave + Candidate APIs fail closed when feature/module unavailable | **PASS** |
| Multi-tenant isolation / RBAC / manager scope / Setup Console / AI / web↔mobile / DB truth / demo isolation / EN·AR·RTL / session·local-lock | **PASS** (unchanged contracts; this wave did not regress them; physical canary reconfirm on OTA) |
| Remaining legacy nested cream/black migration | **SAFE POST-LAUNCH DEBT** (decide only after correctness green — now green) |

---

## 20260810T082000Z — HR Local Lock Wave 2 parity (PASS · canary OTA · FROZEN)

| Field | Value |
| --- | --- |
| Scope | HR Phases 0–5 local lock: 6-digit PIN setup/unlock/change, Face ID/Touch ID opt-in + PIN fallback, idle/background overlay + privacy cover, operator re-auth recovery (not OTP), Device Security on HR Settings; namespaced `wathefni.hr.pin|biometric|autolock.*` bound to `company:user_id`; separate AuthProviders/tokens/endpoints preserved |
| Backend | None (JS/OTA only — native SecureStore/LocalAuthentication already in binary) |
| Not in scope | Session merge · Phase 6 · HR push · employee SecureStore reuse · `/app/device-security` card on HR |
| Ship | OTA **`8b49fe0c-f9cc-43d9-bc70-819d5b7b09c2`** · runtime 0.3.0 · canary · iOS `019feac7-4458-702c-b7ca-60a2af754868` |
| Gates | verify-hr-local-lock-parity · verify-hr-settings-operator-device · tsc |
| Freeze | `.cursor/rules/hr-mobile-local-lock-freeze.mdc` |
| Debt | `ops/HR_MOBILE_LOCAL_LOCK_CONTRACT_DEBT.md` |
| Next | Physical Face ID/auto-lock QA on canary HR; remaining debt as listed |
| Verdict | **PASS** (ship · frozen) |

---

## 20260810T081200Z — HR Delivery Alerts quiet More monitor (PASS · canary OTA · FROZEN)

| Field | Value |
| --- | --- |
| Scope | Quiet read-only More monitor; non-task outbound states; canonical `has_task` / `hr_task_id` dedupe; no Home/Inbox priorities emit; cream/black; capability = HR Tasks read (`payroll.read` included); no resolve/resend; `delivery_failed` vocab; demo `EXPO_PUBLIC_HR_DELIVERY_ALERTS_DEMO=1` |
| Backend | `exclude_linked_tasks` on outbound list/count + mobile queue; priorities omit `delivery_alerts`; backup `/opt/wathefni/backups/hr-delivery-alerts-mobile-20260810T081127Z` |
| Not in scope | Mutations · resend · task resolve from alerts · Home/Inbox surface · full web Alerts & Delivery |
| Ship | OTA **`8b6d1b88-534a-4ca1-a599-bbec31360a92`** · runtime 0.3.0 · canary · iOS `019feaba-c5dc-7964-89c6-d9ee7c36ade1` |
| Gates | verify-hr-delivery-alerts-monitor · verify-hr-more-launcher · tsc · orchestrator health 200 |
| Freeze | `.cursor/rules/hr-mobile-delivery-alerts-freeze.mdc` |
| Debt | `ops/HR_MOBILE_DELIVERY_ALERTS_CONTRACT_DEBT.md` |
| Next | More destination audit complete — future Alerts & Delivery converge folds under Tasks only with `has_task` dedupe |
| Verdict | **PASS** (ship + demo · frozen) |

---

## 20260810T080000Z — HR Settings operator+device (PASS · canary OTA)

| Field | Value |
| --- | --- |
| Scope | Cream/black Settings: identity + human role/scope + My Access (workspaces); locale single control; refresh `/me`; confirmed Sign out (More+Settings) + Sign out all; Switch to Employee when session exists; web note; no company writers / push / PIN |
| Backend | Existing `/me` + logout only — no new settings APIs |
| Not in scope | Setup Console · web Settings writers · Employee Settings merge · HR push/PIN/biometric |
| Ship | OTA **`f19202cf-6a31-46d8-8bcd-7c580a928bb7`** · runtime 0.3.0 · canary · iOS `019feab0-1700-79ca-9075-0dba0621ce89` |
| Gates | verify-hr-settings-operator-device · tsc |
| Debt | `ops/HR_MOBILE_SETTINGS_CONTRACT_DEBT.md` |
| Next | Delivery Alerts quiet More monitor (locked + frozen) |
| Verdict | **PASS** (ship) |

---

## 20260810T075200Z — HR Tasks open follow-up queue (PASS · canary OTA)

| Field | Value |
| --- | --- |
| Scope | Open-only queue; Home+Inbox+More same truth; `/hr/tasks/{taskId}` detail; Mark done via scoped canonical `resolve_hr_task` + handoff side effects; no dismiss/assign; remove `due_at`; demo `EXPO_PUBLIC_HR_TASKS_DEMO=1` |
| Backend | `get_hr_task` scope load; `mobile_hr_task_resolve`; `hr_tasks.actions` includes `resolve` when manage; web resolve also scope-gated; backup `/opt/wathefni/backups/hr-tasks-mobile-20260810T075125Z` |
| Not in scope | Done/dismissed history · dismiss · assign · Delivery Alerts merge |
| Ship | OTA **`ff01bbac-cb04-4e7f-8d82-701c95234835`** · runtime 0.3.0 · canary · iOS `019feaa8-b375-79d7-b466-5b7ad739e550` |
| Gates | verify-hr-tasks-follow-ups · tsc · smoke-test-hr3-mobile-data · orchestrator health 200 |
| Debt | `ops/HR_MOBILE_TASKS_CONTRACT_DEBT.md` |
| Next | Settings audit (locked questions before redesign) — canvas `hr-settings-workflow-audit` |
| Verdict | **PASS** (ship + demo) |

---

## 20260810T073200Z — HR Document Reviews needs_review queue (PASS · canary OTA)

| Field | Value |
| --- | --- |
| Scope | Default/list = `needs_review` only; Home/Inbox/Document Reviews share `document_reviews` via `mobile_document_reviews`; compliance detail preview/download + confirm → `compliance_mark_reviewed` + `expected_status`; no Send Reminder; onboarding fan-out only when compliance module off (preview → `/hr/onboarding/{key}`); cream/black; demo `EXPO_PUBLIC_HR_DOCUMENTS_DEMO=1` |
| Backend | `operator_mobile_data.py` `mobile_document_reviews` + priorities `document_reviews`; backup `/opt/wathefni/backups/hr-documents-mobile-20260810T073143Z` |
| Not in scope | Full register browse · Send Reminder · bulk review · onboarding Accept/Waive on Documents |
| Ship | OTA **`060f3ee2-0fb9-45e6-b521-70b623d7b313`** · runtime 0.3.0 · canary · iOS `019fea99-44d8-70ee-b25a-02195cd98dcb` |
| Gates | verify-hr-documents-reviews · tsc · orchestrator health 200 |
| Debt | `ops/HR_MOBILE_DOCUMENTS_CONTRACT_DEBT.md` |
| Next | HR Tasks audit (locked questions before redesign) — canvas `hr-tasks-workflow-audit` |
| Verdict | **PASS** (ship + demo) |

---

## 20260810T071200Z — HR Onboarding HR-actionable review (PASS · canary OTA)

| Field | Value |
| --- | --- |
| Scope | Queue/Home/Inbox = `being_reviewed` only; Accept+Waive; file preview; bank ESS handoff; company mutate allowlist on `review`; People chip → `/hr/onboarding/{key}`; demo `EXPO_PUBLIC_HR_ONBOARDING_DEMO=1` |
| Backend | `mobile_onboarding_list/detail` + priorities via same list; `operator_mobile` review uses `onboarding_hr_mutate_enabled_for_company`; backup `/opt/wathefni/backups/hr-onboarding-mobile-20260810T071132Z` |
| Not in scope | Remind, start/restart, ownership rails, completion, bank ESS approve, uploads, bulk admin |
| Ship | OTA **`1f3000a8-cdbd-4bc5-b882-e640d6dd798f`** · runtime 0.3.0 · canary · iOS `019fea84-3a08-7f06-8ff9-88415d6b149c` |
| Gates | verify-hr-onboarding-review · tsc · orchestrator health 200 |
| Debt | `ops/HR_MOBILE_ONBOARDING_CONTRACT_DEBT.md` |
| Next | Document Reviews audit (locked questions before redesign) |
| Verdict | **PASS** (ship + demo) |

---

## 20260810T065700Z — HR Shifts decision-first companion (PASS · canary OTA)

| Field | Value |
| --- | --- |
| Scope | Needs Attention (pending swaps) + Today (Kuwait day, read-only); both-sides swap detail; Home/Inbox `shift_swap_decisions`; demo `EXPO_PUBLIC_HR_SHIFTS_DEMO=1` |
| Backend | `build_mobile_priorities` emits swaps; `_attach_swap_shifts` on list/detail; destination `/shifts`; backup `/opt/wathefni/backups/hr-shifts-mobile-20260810T065619Z` |
| Not in scope | Week board, create/cancel/reschedule, templates, publishing, rotations, coverage, PAM, recon |
| Ship | OTA **`757a1b7b-0094-4a52-86a5-2f6ab7e251ff`** · runtime 0.3.0 · canary · iOS `019fea75-dea3-7964-b226-a9a67f461dd6` |
| Gates | verify-hr-shifts-companion · tsc · orchestrator health 200 |
| Debt | `ops/HR_MOBILE_SHIFTS_CONTRACT_DEBT.md` |
| Next | Onboarding audit (no redesign until locked) |
| Verdict | **PASS** (ship + demo) |

---

## 20260810T064050Z — HR Attendance exception-first (PASS · canary OTA · UX FROZEN)

| Field | Value |
| --- | --- |
| Scope | Mobile Attendance as exception-first surface on shared Ops truth: Today + Unresolved (92d API window); Ops kinds; Request correction → pending review; demo via `EXPO_PUBLIC_HR_ATTENDANCE_DEMO=1` |
| Backend | Deployed `attendance_row_is_exception` / `attendance_exception_kind` + `status=exceptions`; Home priorities use mobile attendance items; backup `/opt/wathefni/backups/hr-attendance-mobile-20260810T063952Z` |
| Not in scope | Full web Ops board, bulk/import/capture/payroll boards, Ops dual/apply HTTP on mobile |
| Ship | OTA **`130f2835-c810-49e9-be21-1ad0bbf5cb01`** · runtime 0.3.0 · canary · iOS `019fea67-0b44-723f-bbf2-e8fe17efcff2` |
| Gates | verify-hr-attendance-exceptions · tsc · orchestrator health 200 |
| Freeze | UX frozen this pass — `.cursor/rules/hr-mobile-attendance-ux-freeze.mdc` |
| Debt | `ops/HR_MOBILE_ATTENDANCE_CONTRACT_DEBT.md` (92d lookback · correct_attendance_record · no Ops exception_id/history · Ops-only kinds · dual count sources) |
| Verdict | **PASS** (ship + demo); **do not expand Attendance** while Shifts+ audit continues |

---

## 20260809T133500Z — HR Home visual parity (PASS · physical review)

| Field | Value |
| --- | --- |
| Scope | Employee Wordmark/AmbientCard/ListRow/StatusChip Home; human statuses; tab labels via employee i18n |
| Not in scope | People/Inbox/Hiring/More redesign; freezing HR ambient semantics |
| Ship | OTA **`b471b546-cb9b-45b3-8a04-d2958838adce`** · runtime 0.3.0 · canary |
| Gates | verify-hr-home-parity · verify-hr-shell-ia · unified-principals · tsc |
| Verdict | **PASS** (ship); stop for owner physical inspect |

---

## 20260809T131800Z — HR IA foundation shell (PASS)

| Field | Value |
| --- | --- |
| Scope | Home · People · Inbox · Hiring · More; sparse priority Home; Employee tab chrome |
| Not in scope | Module redesigns, fake urgency, AI Recruiter root tab |
| Ship | OTA **`fd021242-b38f-4132-97ea-264f465ca2a9`** · runtime 0.3.0 · canary |
| Gates | verify-hr-shell-ia · unified-principals · tsc |
| Evidence | `ops/evidence/hr-mobile-ia-foundation-20260809/` |
| Verdict | **PASS** (foundation) |

---

## 20260809T130402Z — HR shell post Work-email crash (PASS fix)

| Field | Value |
| --- | --- |
| Symptom | Work email login succeeded then immediate crash |
| Crash | `useAuth must be used within AuthProvider` at `app/(tabs)/_layout.tsx` |
| Root cause | Post-auth shell swap mounted Employee tabs without Employee AuthProvider (URL still `/`) |
| Fix | Redirect/Slot guard until `/hr`; work-email `router.replace('/hr')` before `selectMode('hr')` |
| Ship | OTA **`e6ef7513-4a84-456d-8ab3-ba13cf133b8e`** · runtime 0.3.0 · canary |
| Gates | hr-shell-postauth + unified-principals + capability + push-storm + /me Home data |
| Evidence | `ops/evidence/unified-app-hr-shell-postauth-crash-20260809T130402Z/` |
| Physical | Force-quit/reopen → Work email → HR Home |
| Verdict | **PASS** (fix + OTA) |

---

## 20260809T124804Z — Unified sign-in OTA delivery fix (PASS delivery)

| Field | Value |
| --- | --- |
| Symptom | Canary 0.3.0 force-quit still showed Phone + Activation code only (no Phone \| Work email switcher) |
| Prior OTA | `99b969d9-4089-49cb-80f3-2e05c203ffba` (canary / runtime 0.3.0) — **did reach** this build/channel, but baked `EXPO_PUBLIC_HR_WORKSPACE_ENABLED` unset → `PrincipalGate` forced `{kind:'employee'}` → `EmployeeShell` ActivationView without method switcher |
| Root cause | `eas update` does not inherit `eas.json` build.env; OTA overwrote embedded JS that had the flag |
| Fix | `app.config.js` defaults HR workspace to `1`; `hrWorkspaceEnabled()` also falls back to `extra.unifiedApp.hrWorkspace`; republish OTA with flag forced |
| Route | `ModeRedirect` mounts `UnsignedEntry` when `shell.kind === 'unsigned'` (Phone \| Work email) |
| Ship | OTA group **`e046b071-f3ea-45a8-a515-f5499d1c156f`** · iOS update `019fe690-e682-7bfd-a223-701f33b920ae` · runtime **0.3.0** · channel **canary** · matches native build `fa70005b-6eb4-4481-860f-9c4013d92a93` |
| Bundle proof | published `dist` contains `methodPhone` / `Work email` / `UnsignedEntry`; web minify shows `String("1")` for HR flag |
| Gates | `verify-unified-principals.py` 25/25 |
| Physical | Force-quit + reopen 0.3.0 to fetch OTA (owner eyeball) |
| Verdict | **PASS** (canary delivery/routing) |

---

## 20260809T084213Z — PIN unlock layout polish (PASS)

| Field | Value |
| --- | --- |
| Scope | Vertical balance, breathing under status bar, softer PIN surface, intentional dots |
| Files | PinView · BiometricOptInView · LocalUnlockOverlay (no double SafeArea) |
| Auth | Unchanged |
| Ship | OTA b99b5661-2b62-4f20-abec-1783b3c5aa59 runtime 0.2.0 |
| Evidence | ops/evidence/employee-app-pin-unlock-layout-20260809T084213Z/ |
| Verdict | **PASS** |

---

## 20260809T083902Z — Push tray copy polish (PASS)

| Field | Value |
| --- | --- |
| Scope | Human tray EN/AR; friendly dates/times; no ISO; no Open/HR jargon CTAs |
| Ship | `employee_push_tray.py` prod restart (JS unchanged) |
| Gates | smoke-test-employee-push-tray PASS |
| Evidence | `/Users/azizalmulla/Desktop/claw/ops/evidence/employee-app-push-tray-copy-20260809T083902Z/` |
| Verdict | **PASS** |

---

## 20260809T082509Z — Access regression after push permission (PASS fix · physical pending)

| Field | Value |
| --- | --- |
| Symptom | App access unavailable after Allow notifications (Aziz iPhone) |
| Root cause | PushLifecycle register storm → DB pool exhausted → false `employee_app_not_enabled_for_company` |
| Entitlements | Unchanged — WATHEFNI `employee_app` enabled; Aziz allowlisted/active |
| Push causal? | Trigger yes / entitlement change no |
| Fix | Single-flight PushLifecycle + soft API no shell block + server 503 on pool errors |
| Ship | OTA `754b9114-1b49-40db-93ce-127e33e65f09` + orchestrator app.py restart |
| Evidence | `/Users/azizalmulla/Desktop/claw/ops/evidence/employee-app-access-regression-20260809T082509Z/` |
| Physical | **PENDING** access re-verify before push event walk |
| Verdict | **PASS** (root cause + automated fix); physical TBD |

---

## 20260809T075811Z — Push notifications UX wave (PASS automated · physical pending)

| Field | Value |
| --- | --- |
| Scope | Default-on after OS permission; Settings opt-out; tray copy; badge sync; activation Inbox-only; payslip/bank/docs push |
| Mobile | Opt-out prefs · PushLifecycle auto-register · syncInboxBadge · Settings manage/disable |
| Server | `employee_push_tray.py` · ladder skip activation · collapse/timeSensitive · payslip+bank+compliance expiring |
| Gates | push-sound PASS · capability GREEN · follow-through 14 · push-tray smoke PASS |
| Ship | OTA JS + orchestrator canary deploy (`WATHEFNI_PUSH_NOTIFICATIONS` on) |
| Physical | **PENDING** (FG/BG/killed/tap/badge/sound/dupe on Aziz/Talal) |
| Evidence | `ops/evidence/employee-app-push-ux-wave-20260809T075811Z/` |
| Rollback | OTA prior · or `WATHEFNI_PUSH_NOTIFICATIONS=off` |
| Verdict | **PASS** (automated); physical canary TBD |

---

## 20260809T071200Z — iOS 26 Icon Composer (FAIL ship · assets ready)

| Field | Value |
| --- | --- |
| Current path | Legacy PNG `expo.icon` / AppIcon.appiconset on Xcode 15.4 builds |
| Auto-adapt | **Yes** (iOS 26 Liquid Glass on legacy PNG) |
| Composer package | `assets/WathefniAppIcon.icon` (cream fill + badge layer; specular/translucency/glass off) |
| Build attempt | `4146bebf…` on `macos-sequoia-15.6-xcode-26.2` → XCODE_BUILD_ERROR (SDK 51 vs Xcode 26) |
| Physical after | Blocked (no IPA) |
| Evidence | `ops/evidence/employee-app-icon-composer-*/` |
| Verdict | **FAIL** (ship); Composer assets + gated plugin ready for SDK 54+ |

---

## 20260809T072129Z — Expo SDK 54 upgrade + Icon Composer iOS (PASS IPA · physical pending)

| Field | Value |
| --- | --- |
| Before | Expo ~51 / RN 0.74.5 / React 18.2 / runtime 0.1.0 |
| After | Expo ~54 / RN 0.81.5 / React 19.1 / runtime **0.2.0** · newArch **false** · Reanimated 3.19 |
| iOS | `83f5955b-f9c7-45a7-a4c9-d09f696a2dcf` · Xcode 26.2 · buildNumber 22 |
| Bundled | Icon Composer `WathefniAppIcon` + `wathefni_default.wav` (IPA verified) |
| Regression | Automated gates PASS; Schedule RTL dirty-tree pre-existing FAIL noted |
| Physical icon | **PENDING** (no handset) |
| Evidence | `ops/evidence/employee-app-sdk54-upgrade-20260809T072129Z/` |
| Rollback | Restore SDK51 before artifacts; runtimeVersion isolates 0.1.0 vs 0.2.0 |
| Verdict | **PASS** (build); physical Home Screen TBD |

---

## 20260809T065323Z — iOS native retry flat icon + sound 040 (PASS)

| Field | Value |
| --- | --- |
| Scope | Retry iOS native after Expo Starter upgrade. Assets unchanged (flat cream icon + `wathefni_default.wav`). |
| Quota preflight | `abdulazizalmullas-team` plan **Starter** `active` (GraphQL) before submit |
| Build | iOS `78bb78be-dde2-4d8c-b7db-449e6d97a59f` · buildNumber 19 · finished |
| Link | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/78bb78be-dde2-4d8c-b7db-449e6d97a59f |
| Icon+sound | Included (icon sha `9066753b…`, bundled `wathefni_default.wav`) |
| Evidence | `ops/evidence/employee-app-ios-flat-sound040-20260809T065323Z/` |
| Verdict | **PASS** |

---


## 20260809T064004Z — Flat cream icon + push sound 040 (PASS assets · Android building)

| Field | Value |
| --- | --- |
| Scope | Remove icon frame/chrome (full-bleed flat cream `#FEF0D6` + solid black badge, system mask only). Swap push tone to Universfield `040-493469`. Android channel → `wathefni_default_v2`. |
| Canonical | `assets/brand/wathefni-app-icon-approved-master.png` sha `9066753b…` (= icon/adaptive) |
| Sound | `assets/sounds/push/wathefni_default.wav` from `universfield-new-notification-040-493469.mp3` (~1.07s) |
| Gates | verify-push-sound PASS · verify-semantic-feedback PASS |
| Evidence | `ops/evidence/employee-app-icon-flat-sound040-20260809T064004Z/` |
| Android | EAS `82f00604-687b-4d00-a5bc-1ca8b92de66d` (versionCode 11) |
| iOS | **Blocked** — EAS Free plan iOS quota exhausted until 2026-09-01. Need plan upgrade or local Xcode build. |
| Ship | Native rebuild required (icon + bundled sound). Orchestrator `channelId` → `wathefni_default_v2` (deploy for Android). |
| Verdict | **PASS** (assets); Android native in flight; iOS pending quota |

---


## 20260809T062852Z — Legacy logo audit (PASS)

| Field | Value |
| --- | --- |
| Scope | Full Employee App logo audit. Replaced legacy serif-W splash. Removed unused previews/duplicates. Canonical badge only. |
| Canonical | `assets/brand/wathefni-app-icon-approved-master.png` (= icon/adaptive) |
| Evidence | `ops/evidence/employee-app-logo-audit-20260809T062852Z/` |
| Verdict | **PASS** |

---

## 20260809T061905Z — App icon exact approved master (PASS)

| Field | Value |
| --- | --- |
| Scope | Stop redrawing icon. Ship byte-identical approved master as `icon.png` + `adaptive-icon.png`. |
| Cause of blunder | Connected-component extract + resize/recomposite (~61% pixels differed vs master). |
| Source | `assets/brand/wathefni-app-icon-approved-master.png` (= `assets/icon.png`) sha `85884e9b…` |
| Channel | Native iOS `74d71dbb-…` (Android build uploading) |
| Evidence | `ops/evidence/employee-app-icon-master-exact-20260809T061905Z/` |
| Verdict | **PASS** |

---

## 20260809T060401Z — Icon bottom-anchor + push canary enable (PASS assets)

| Field | Value |
| --- | --- |
| Scope | Bottom-anchored Wathefni icon. Enable push registration OTA + server `WATHEFNI_PUSH_NOTIFICATIONS=on` for sound test. |
| Channel | OTA `c62ee5b8-9d61-4aaa-a197-3612f15c7e96` · iOS native `02779570-…` · Android `7116970a-…` |
| Push | No Aziz token yet — needs Settings → Push on after OTA/native |
| Evidence | `ops/evidence/employee-app-icon-bottom-anchor-20260809T060401Z/` |
| Verdict | **PASS** (icon); push send pending device registration |

---

## 20260809T054307Z — Wathefni app icon (PASS assets · native building)

| Field | Value |
| --- | --- |
| Scope | Replace app icon with owner Wathefni mark. Full-bleed cream `#FEF0D6`, crop brackets stripped, Android adaptive safe-zone mark, white notification glyph. |
| Channel | Native rebuild required (icons not OTA). iOS `eb2653f6-…` · Android `f0ab7d98-…` |
| Evidence | `ops/evidence/employee-app-icon-20260809T054307Z/` |
| Verdict | **PASS** (assets); install new native binary for home-screen icon |

---

## 20260809T053857Z — In-app haptics only (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Remove in-app UI tones (`snap`/`success`/`warning`/`error`) + `expo-av`. Keep semantic haptics. Push `wathefni_default` unchanged. |
| Channel | Canary OTA `517be51a-902e-482a-8a78-869a16f0b8d4` · runtime `0.1.0` |
| Rollback | `bd9e4015-e503-4f6d-9026-f1cd2a83a6d4` |
| Gates | semantic-feedback PASS · push-sound PASS · density PASS · capability PASS · auth-wave2 dist PASS · tsc PASS |
| Evidence | `ops/evidence/employee-app-haptics-only-20260809T053857Z/` |
| Verdict | **PASS** |

---

## 20260809T051843Z — Feedback tune (PASS canary · sound needs native)

| Field | Value |
| --- | --- |
| Scope | Strengthen semantic haptics (Soft/Medium/Heavy + CTA press). Restrained original UI tones on week snap / success / warning / error only. No visuals/architecture/business logic. |
| Channel | Canary OTA `48be9a0a-22d5-4649-8dc7-4cedcdf1af8b` · runtime `0.1.0` |
| Native | iOS build `78372a77-2dce-4c41-99c5-7525d8847f01` (expo-av for sound; haptics live via OTA alone) |
| Rollback | `afb8371a-75ab-42af-a3d5-0f776e5488aa` |
| Gates | semantic-feedback PASS · density PASS · capability PASS · color PASS · auth-wave2 dist PASS · tsc PASS |
| Evidence | `ops/evidence/employee-app-feedback-tune-20260809T051843Z/` |
| Verdict | **PASS** (haptics OTA; audible after native install) |

---

## 20260809T051008Z — Native micro-feedback (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Native micro-feedback only. Central semantic layer (`selection` / `lightImpact` / `success` / `warning` / `error`). No visual redesign. Throttle/dedupe; Schedule tap+swipe-settle only; no PremiumButton blanket. |
| Channel | Canary OTA `afb8371a-75ab-42af-a3d5-0f776e5488aa` · runtime `0.1.0` |
| Rollback | `96703a6f-3f52-4c1f-8e64-8aa72000ad7e` |
| Gates | semantic-feedback PASS · density PASS · capability PASS · color PASS · auth-wave2 dist PASS · tsc PASS |
| Evidence | `ops/evidence/employee-app-native-feedback-20260809T051008Z/` |
| Verdict | **PASS** (physical iPhone not attached this session — canary device pull) |

---

## 20260809T050444Z — Onboarding cards restore (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Visual only. Restore lifecycle-colored cards (yellow action / pink correction / soft-blue progress+review+handled / cream completed). Keep quiet Preview/History. Authority/fixture unchanged. |
| Channel | Canary OTA `96703a6f-3f52-4c1f-8e64-8aa72000ad7e` · runtime `0.1.0` |
| Fixture | unchanged `WATHEFNI-9655237101` |
| Rollback | `28a28073-d4bf-47c1-ba16-f95f4c69ffbc` |
| Gates | density PASS · capability PASS · color PASS · auth-wave2 dist PASS |
| Evidence | `ops/evidence/employee-app-onboarding-cards-20260809T050444Z/` |
| Verdict | **PASS** |

---

## 20260809T050027Z — Onboarding hierarchy refine (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Onboarding visual hierarchy only. Soft-blue progress; pink only on correction; cream Your actions; quieter review/handled/completed accents; Preview/History as inline text. Lifecycle/fixture/authority unchanged. |
| Channel | Canary OTA `28a28073-d4bf-47c1-ba16-f95f4c69ffbc` · runtime `0.1.0` |
| Fixture | unchanged `WATHEFNI-9655237101` |
| Rollback | `da7d44f0-69d2-4379-80a6-77ef7a85ee19` |
| Gates | density PASS · capability PASS · color PASS · auth-wave2 dist PASS |
| Evidence | `ops/evidence/employee-app-onboarding-hierarchy-20260809T050027Z/` |
| Verdict | **PASS** |

---

## 20260809T045135Z — Onboarding visual + interaction (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Onboarding visual + open latency only. Cream ledger hierarchy; one lilac progress card; Your actions strongest; review/handled/completed quieter; selective life marks; soft upload refresh; latest-wins preview. Wave 2A / completion / upload / bank CTA authority unchanged. |
| Channel | Canary OTA `da7d44f0-69d2-4379-80a6-77ef7a85ee19` · runtime `0.1.0` |
| Fixture | `WATHEFNI-9655237101` · phone `9655237101` · code `622949` · `ops-seed-onboarding-visual-fixture.py` · 3 your / 2 review / 1 handled / 7 completed |
| Rollback | `f226bdf5-d48e-49ef-b172-7c3672a0723e` · fixture `--cleanup` |
| Gates | density PASS · capability PASS · auth-wave2 dist PASS |
| Evidence | `ops/evidence/employee-app-onboarding-visual-20260809T045135Z/` |
| Verdict | **PASS** |

---

## 20260809T043924Z — Auth Wave 2 activation restore (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Restore PIN/Face ID/auto-lock. Masters default ON unless explicit `0`. Remove Aziz/Talal employee allowlists. Persist flags via EAS production env + `app.config.js` + publish script. |
| Channel | Canary OTA `f226bdf5-d48e-49ef-b172-7c3672a0723e` · runtime `0.1.0` |
| Dist proof | `pin-unlock-effective:on` · `bio-unlock-effective:on` · `al-lock-effective:on` |
| Rollback | `cf1cd9a5-39fc-4e8f-a603-fb6679b90b63` |
| Evidence | `ops/evidence/employee-app-auth-wave2-restore-20260809T043924Z/` |
| Verdict | **PASS** |

---

## 20260809T042744Z — Bank hierarchy cleanup (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Bank hierarchy only. One Pending change section; quiet non-yellow review mark; primary/secondary actions; smaller safety note. Authority/lifecycle/masking/routes unchanged. |
| Channel | Canary OTA `cf1cd9a5-39fc-4e8f-a603-fb6679b90b63` · runtime `0.1.0` |
| Rollback | `997f5309-4818-46e6-8e48-348093ccebd8` |
| Gates | density PASS · capability PASS · color PASS |
| Evidence | `ops/evidence/employee-app-bank-hierarchy-20260809T042744Z/` |
| Verdict | **PASS** |

---

## 20260809T042111Z — Bank visual + interaction (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Bank visual + open/edit/submit latency only. Cream ledger; one butter account surface; calm life marks (action/review/settled); softer employee status copy. Soft upload refresh; latest-wins evidence open. Bank ESS authority/lifecycle/IBAN/masking/routes unchanged. |
| Channel | Canary OTA `997f5309-4818-46e6-8e48-348093ccebd8` · runtime `0.1.0` |
| Fixture | Noura effective+pending_hr · 7001 pending_payroll · 7002 needs_correction · 7003 applied · `ops-seed-bank-visual-fixture.py` |
| Rollback | `0561f73f-4b2b-4592-896c-874244ab2639` · fixture `--cleanup` |
| Gates | density PASS · capability PASS · color PASS |
| Evidence | `ops/evidence/employee-app-bank-visual-20260809T042111Z/` |
| Verdict | **PASS** |

---

## 20260809T041123Z — Documents Current/History density (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Density refine only: Current denser (name→expiry→quiet Reviewed→chevron); no renew on healthy docs; quieter History (chevron, no View); Attention stays strongest; fix `personal_photo` missing i18n. |
| Channel | Canary OTA `0561f73f-4b2b-4592-896c-874244ab2639` · runtime `0.1.0` |
| Rollback | `c4ae8e90-dbae-495f-8887-019386dc761b` |
| Gates | density PASS · capability PASS · color PASS · keysets match · tsc clean |
| Evidence | `ops/evidence/employee-app-documents-density-20260809T041123Z/` |
| Verdict | **PASS** |

---

## 20260809T040453Z — Documents visual + interaction (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Documents visual + open latency only. Cream ledger rows; pink accent only on Needs attention; green healthy status pills; quieter History. Latest-open-wins (cancel prior download); row press opens; soft invalidate after renew. IA / OCR / renew authority unchanged. Noura fixture for populated judgment. |
| Channel | Canary OTA `c4ae8e90-dbae-495f-8887-019386dc761b` · runtime `0.1.0` |
| Fixture | `WATHEFNI-96550010001` · phone `96550010001` · code `561188` · seed `ops-seed-docs-visual-fixture.py` · 3 attention / 5 current / 16 files |
| Rollback | `4ab57e78-af3d-4f0b-8986-d7f9c0025361` · fixture `--cleanup` |
| Gates | density PASS · capability PASS · color PASS · hierarchy 7/7 · tsc clean |
| Evidence | `ops/evidence/employee-app-documents-visual-20260809T040453Z/` |
| Verdict | **PASS** |

---

## 20260809T035953Z — Page scroll bottom limit (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Whole-app scroll end: stop double-counting tab bar height in `PageScrollView` padding; keyboard insets opt-in only; no automatic content inset stacking; Home no longer overrides bottom padding. |
| Channel | Canary OTA `4ab57e78-af3d-4f0b-8986-d7f9c0025361` · runtime `0.1.0` |
| Rollback | `8851af5b-1fc1-4d24-b610-08631226f304` |
| Gates | capability PASS (scroll checks) · tsc clean |
| Evidence | `ops/evidence/employee-app-scroll-limit-20260809T035953Z/` |
| Verdict | **PASS** (device confirm: scroll stops after last content + small breathing room) |

---

## 20260809T035506Z — Inbox visual + interaction (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Inbox visual + tap latency only. Cream ledger rows (title/body/time), restrained unread accent, quieter collapsed Account activity. Immediate nav (latest tap wins); mark-read optimistic after push; soft invalidate; leave_decision + flow defaults. IA/dedupe/supersede unchanged. Synthetic Noura fixture for density. |
| Channel | Canary OTA `8851af5b-1fc1-4d24-b610-08631226f304` · runtime `0.1.0` |
| Fixture | `WATHEFNI-96550010001` · phone `96550010001` · code `156807` · seed `ops-seed-inbox-visual-fixture.py` · 32 msgs / 8 unread |
| Rollback | `a3ed510a-df54-48e6-b13c-72966729be61` · fixture `--cleanup` |
| Gates | density PASS · capability PASS · tsc clean |
| Evidence | `ops/evidence/employee-app-inbox-visual-20260809T035506Z/` |
| Verdict | **PASS** (device rapid-tap stress pending canary pull) |

---

## 20260809T034436Z — Payslips ledger + PDF copy (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Restore yellow detail hero. One PDF-unavailable footnote. Root list → flat cream ledger (month/period/amount, hairlines, newest butter accent only). Year groups + pagination unchanged. |
| Channel | Canary OTA `a3ed510a-df54-48e6-b13c-72966729be61` · runtime `0.1.0` |
| Rollback | `c8d7076b-8ad1-42fe-9b3a-908dd382bb0d` |
| Gates | density PASS (ledger check) · tsc clean |
| Evidence | `ops/evidence/employee-app-payslips-ledger-20260809T034436Z/` |
| Verdict | **PASS** |

---

## 20260809T033846Z — Payslips visual wave (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Payslips visual only: cream foundation, month/amount/issued hierarchy, intentional open-year treatment, CalmNote empty, quiet detail surface. Year grouping + keyset pagination preserved. Synthetic Noura fixture 30 slips (2026/2025/2024) for populated judgment. Aziz/Talal untouched. |
| Channel | Canary OTA `c8d7076b-8ad1-42fe-9b3a-908dd382bb0d` · runtime `0.1.0` |
| Fixture | `WATHEFNI-96550010001` · phone `96550010001` · code `539840` · seed `ops-seed-payslip-visual-fixture.py` |
| Rollback | `ece7fa6a-14ae-4283-8f03-6d0a12d37b4b` · fixture `--cleanup` |
| Gates | color PASS · density PASS · tsc clean · seed shape OK (24 + has_more) |
| Evidence | `ops/evidence/employee-app-payslips-visual-20260809T033846Z/` |
| Verdict | **PASS** |

---

## 20260809T025330Z — Leave visual wave (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Leave root + history visual polish: green entitlement card, Approved/Requested/Rejected brand pills (green/yellow/pink), CalmNote empties, black Request CTA, black history filters. No layout copy of Schedule; no authority change. |
| Channel | Canary OTA `ece7fa6a-14ae-4283-8f03-6d0a12d37b4b` · runtime `0.1.0` |
| Rollback | `edab3610-a184-42c2-bb6b-9d1ca37d73b1` |
| Gates | color PASS · density PASS · tsc clean |
| Evidence | `ops/evidence/employee-app-leave-visual-20260809T025330Z/` |
| Verdict | **PASS** |

---

## 20260809T024939Z — Schedule powder blue + Home profile tap (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Home avatar opens Profile. Schedule planned surfaces/chips → soft powder blue `#C5D4F0`; Present/Late/Absent stay green/yellow/pink; selection black; cream ground. No Schedule layout/data/interaction changes. |
| Channel | Canary OTA `edab3610-a184-42c2-bb6b-9d1ca37d73b1` · runtime `0.1.0` |
| Rollback | `ad21acee-d77f-4f71-9b77-b6b46da78ca9` |
| Gates | color PASS · density PASS · tsc clean |
| Evidence | `ops/evidence/employee-app-schedule-blue-profile-20260809T024939Z/` |
| Verdict | **PASS** |

---

## 20260809T023453Z — Attendance history brand pills (PASS canary)

| Field | Value |
| --- | --- |
| Scope | View attendance history uses same Present/Late/Absent brand pills as Schedule |
| Channel | Canary OTA `ad21acee-d77f-4f71-9b77-b6b46da78ca9` · runtime `0.1.0` |
| Rollback | `1ef4f60e-c427-4007-a52e-b3194456d0b7` |
| Evidence | `ops/evidence/employee-app-history-pills-20260809T023453Z/` |
| Verdict | **PASS** |

---


## 20260809T023156Z — Schedule attendance brand pills (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Present/Late/Absent → green/yellow/pink ambient pills on Schedule summary + rows |
| Channel | Canary OTA `1ef4f60e-c427-4007-a52e-b3194456d0b7` · runtime `0.1.0` |
| Rollback | `1426ee18-43b0-4838-b06d-ec5a0b98823e` |
| Evidence | `ops/evidence/employee-app-attendance-pills-20260809T023156Z/` |
| Verdict | **PASS** |

---


## 20260809T022740Z — Open smoothness (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Post-load jank: one Home FadeIn, deferred soft-refresh, shared LoadingState |
| Channel | Canary OTA `1426ee18-43b0-4838-b06d-ec5a0b98823e` · runtime `0.1.0` |
| Rollback | `7356b390-d966-45d2-a24b-272bdb5cdc17` |
| Evidence | `ops/evidence/employee-app-open-smooth-20260809T022740Z/` |
| Verdict | **PASS** |

---


## 20260809T022428Z — Schedule in-cell capsule (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Fix clipped Sunday capsule: in-cell stadium; CalmNote empties (no white empty cards) |
| Channel | Canary OTA `7356b390-d966-45d2-a24b-272bdb5cdc17` · runtime `0.1.0` |
| Rollback | `dff580af-bca4-44dd-94b8-97c5282b9968` |
| Evidence | `ops/evidence/employee-app-capsule-incell-20260809T022428Z/` |
| Verdict | **PASS** |

---


## 20260809T023924Z — Schedule visual redesign populated fixture (READY)

| Field | Value |
| --- | --- |
| Scope | Synthetic Schedule fixture for physical judgment of the redesign with realistic Today / Upcoming / Recent data. **No design change.** Aziz/Talal untouched. |
| Identity | `WATHEFNI-96550010001` Noura · phone `96550010001` · activation `703012` (expires ~2026-08-10 02:40Z) |
| Shape | Today 09:00–17:00 Salmiya + Present check-in · 3 upcoming (distinct sites/times) · recent Present / Late-by-12 / Absent · summary 3/1/1 |
| Channel | Data-only seed via `ops-seed-schedule-visual-fixture.py` · no OTA |
| Cleanup | `.venv/bin/python ops-seed-schedule-visual-fixture.py --cleanup` |
| Evidence | `ops/evidence/employee-app-schedule-visual-fixture-20260809T023924Z/` |
| Verdict | **READY_FOR_PHYSICAL_JUDGMENT** |

---


## 20260809T021502Z — Schedule visual redesign (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Kill Present/Late/Absent KPI tiles → quiet 30d line; QuietEmpty day/upcoming; taller week capsule; HR footnote; Home untouched |
| Channel | Canary OTA `dff580af-bca4-44dd-94b8-97c5282b9968` · runtime `0.1.0` · no native build |
| Rollback | `5263ab51-5a7b-4ed5-8f64-755e09e4a370` |
| Gates | density PASS · capability GREEN · tsc clean |
| Evidence | `ops/evidence/employee-app-schedule-redesign-20260809T021502Z/` |
| Verdict | **PASS** |

---


## 20260809T020931Z — LoadingState drop left wordmark (PASS canary)

| Field | Value |
| --- | --- |
| Scope | LoadingState: remove left-aligned Wathefni; centered spinner only |
| Channel | Canary OTA `5263ab51-5a7b-4ed5-8f64-755e09e4a370` · runtime `0.1.0` |
| Rollback | `e0dc5e93-7165-4e6d-a195-033c15dddc11` |
| Evidence | `ops/evidence/employee-app-loading-wordmark-20260809T020931Z/` |
| Verdict | **PASS** |

---


## 20260809T020711Z — Week-strip capsule + LoadingState (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Perfect vertical selected-day capsule; centered premium LoadingState (no giant empty card) |
| Channel | Canary OTA `e0dc5e93-7165-4e6d-a195-033c15dddc11` · runtime `0.1.0` · no native build |
| Rollback | `dd05381d-b2a0-4d59-b0f9-117e71b4b0f7` |
| Gates | density PASS · capability GREEN · tsc clean |
| Evidence | `ops/evidence/employee-app-capsule-loading-20260809T020711Z/` |
| Verdict | **PASS** |

---


## 20260809T015936Z — Visual polish except Home (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Coordinated visual polish: Schedule, histories, Leave, Payslips, Inbox, Documents, Profile, Bank, Onboarding, Settings/Privacy, shared states; **Home untouched** |
| Channel | Canary OTA `dd05381d-b2a0-4d59-b0f9-117e71b4b0f7` · runtime `0.1.0` · no native build |
| Rollback | `c4249469-8c13-4d47-a053-ded2149dc3f3` |
| Gates | density PASS (99) · capability GREEN · tsc clean |
| Evidence | `ops/evidence/employee-app-visual-polish-20260809T015936Z/` |
| Verdict | **PASS** — canary OTA ready; device visual pull optional |

---


## 20260809T014715Z — Phase 5.2: Leave History UI (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Leave → View all history → `/leave/history`; cursor load-older + year/status chips over `/app/leave/history`; compact rows; cancel only for requested\|approved + capability; root unchanged aside from entry |
| Channel | Canary OTA `c4249469-8c13-4d47-a053-ded2149dc3f3` · runtime `0.1.0` · no native build |
| Rollback | `c12f398e-68a6-4c77-8781-6315d2402a92` |
| Gates | density PASS · capability GREEN · tsc clean · year/status contract PASS |
| Evidence | `ops/evidence/employee-app-leave-history-ui-20260809T014715Z/` |
| Verdict | **PASS** — stop after Phase 5.2 |

---

## 20260809T014321Z — Phase 5.1: Attendance History UI (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Schedule → View attendance history → `/schedule/history`; cursor load-older + month chips over `/app/schedule/history`; compact rows; scheduled only when API returns it; root/week strip unchanged aside from entry |
| Channel | Canary OTA `c12f398e-68a6-4c77-8781-6315d2402a92` · runtime `0.1.0` · no native build |
| Rollback | `41afc0af-2aa8-46dd-911e-c94d17941ed1` |
| Gates | density PASS · capability GREEN · tsc clean · month contract PASS |
| Evidence | `ops/evidence/employee-app-attendance-history-ui-20260809T014321Z/` |
| Verdict | **PASS** — stop before Leave History UI |

---

## 20260809T013329Z — Phase 4.3: Leave history backend (PASS)

| Field | Value |
| --- | --- |
| Scope | `GET /app/leave/history` keyset + optional `status`/`date_from`/`date_to`/`year`; same request fields as root; `/app/leave` still ≤50; cancel/balances untouched; no Leave UI; no mobile OTA |
| Backend | deployed · backup `production-pre-employee-leave-history-20260809T013329Z` |
| Mobile OTA | none (backend only) |
| Rollback | BE backup `ROLLBACK.sh` |
| Gates | leave-history smoke PASS (24) · health 200 · `/app/leave` regression PASS |
| Evidence | `ops/evidence/employee-app-leave-history-20260809T013329Z/` |
| Verdict | **PASS** — stop after Phase 4.3 |

---

## 20260809T012444Z — Phase 4.2: Schedule attendance history backend (PASS)

| Field | Value |
| --- | --- |
| Scope | `GET /app/schedule/history` keyset + optional `date_from`/`date_to`; recorded vs canonical scheduled; `/app/workday` unchanged; no Schedule UI; no Leave history; no mobile OTA |
| Backend | deployed · backup `production-pre-employee-schedule-history-20260809T012444Z` |
| Mobile OTA | none (backend only) |
| Rollback | BE backup `ROLLBACK.sh` |
| Gates | schedule-history smoke PASS (23) · health 200 · workday window regression PASS |
| Evidence | `ops/evidence/employee-app-schedule-history-20260809T012444Z/` |
| Verdict | **PASS** — stop before Leave history (4.3) |

---

## 20260809T011927Z — Phase 4.1: Payslips keyset pagination (PASS)

| Field | Value |
| --- | --- |
| Scope | `/app/payslips` `limit`+`cursor`+`has_more`+`next_cursor`; mobile Load earlier under existing year groups; no redesign; Home untouched; Schedule/Leave history APIs not started |
| Backend | deployed · backup `production-pre-employee-payslips-pagination-20260809T011927Z` |
| Mobile OTA | `41afc0af-2aa8-46dd-911e-c94d17941ed1` · runtime `0.1.0` |
| Rollback | BE backup ROLLBACK · FE `f151fbb5-f174-47bc-9c78-4f45c1af5c2f` |
| Gates | pagination smoke PASS · density PASS · capability GREEN · tsc clean |
| Evidence | `ops/evidence/employee-app-payslips-pagination-20260809T011927Z/` |
| Verdict | **PASS** — stop before Schedule/Leave history contracts |

---

## 20260809T011317Z — Phase 3: Leave root UX (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Leave structural only. Balances only when `balances_enabled` + canonical number; subtitle swaps when balances hidden; Current vs Recent history; Show more within ~50 API window; cancel rules unchanged; no year/status filters |
| Channel | Canary OTA `f151fbb5-f174-47bc-9c78-4f45c1af5c2f` · runtime `0.1.0` · no native build |
| Rollback | `3f83d757-7b30-4878-999a-f55e935d21cc` |
| Gates | density PASS · capability GREEN · tsc clean · partition smoke PASS · live Aziz/Talal leave shape PASS |
| Evidence | `ops/evidence/employee-app-leave-root-ux-20260809T011317Z/` |
| Verdict | **PASS** |

---

## 20260809T011008Z — Schedule week strip rapid-tap perf (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Interruptible capsule springs; local latest-wins visual selection; `startTransition` for day panel; memoized Upcoming/Recent so date taps do not rebuild them; haptic throttle; no layout setState |
| Channel | Canary OTA `3f83d757-7b30-4878-999a-f55e935d21cc` · runtime `0.1.0` · no native build |
| Rollback | `088982ab-67bd-4c23-ac50-acb6ae8841c4` |
| Gates | density PASS · capability GREEN · tsc clean |
| Evidence | `ops/evidence/employee-app-schedule-week-strip-perf-20260809T011008Z/` |
| Verdict | **PASS** (device rapid-tap stress pending canary pull) |

---

## 20260809T010425Z — Schedule week strip day selector (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Interactive week strip under Schedule intro; selected-day panel from `/app/workday` window only (today paired; future shifts; past attendance); capsule spring; Phase 2 hierarchy preserved |
| Contract limit | No arbitrary-day API — outside ±30d shows honest unavailable; past has no shift roster in payload |
| Channel | Canary OTA `088982ab-67bd-4c23-ac50-acb6ae8841c4` · runtime `0.1.0` · no native build |
| Rollback | `8db2b731-8c39-40dc-beb0-9c92bba0addd` |
| Gates | density PASS · capability GREEN · tsc clean · day-model smoke PASS |
| Evidence | `ops/evidence/employee-app-schedule-week-strip-20260809T010425Z/` |
| Verdict | **PASS** (device gesture feel pending canary pull) |

---

## 20260809T004858Z — Phase 2: Schedule root UX (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Schedule structural only. Today → Upcoming(5) → Recent(5)+quiet P/L/A; Show more within fetched 30d window; remove hero bloom; no Home redesign; no backend change |
| Channel | Canary OTA `8db2b731-8c39-40dc-beb0-9c92bba0addd` · runtime `0.1.0` · no native build |
| Rollback | `2c8c6f8f-9638-4099-8676-7f046bf56934` |
| Gates | density PASS · capability GREEN · tsc clean · workday contract PASS · live Aziz/Talal shape PASS |
| Evidence | `ops/evidence/employee-app-schedule-root-ux-20260809T004858Z/` |
| Verdict | **PASS** (device visual pull remaining for canary after OTA) |

---

## 20260809T004500Z — Inbox: Earlier → Updates label (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Naming only. Sections: Unread · Updates · Account activity. EN `Updates` / AR `التحديثات`. No authority or filter changes |
| Channel | Canary OTA `2c8c6f8f-9638-4099-8676-7f046bf56934` · runtime `0.1.0` · no native build |
| Rollback | `428d1000-80cb-4f36-83d5-f399af1b85bf` |
| Gates | capability GREEN · EN/AR keys match |
| Verdict | Stopped for owner review |

---

## 20260809T003705Z — Phase 1: activation Inbox supersede (PASS canary)

| Field | Value |
| --- | --- |
| Scope | Stop `app_activation` Inbox multiply on resend: backend hides prior rows (`inbox_hidden`) after new delivery; projection keeps newest only; FE maps `app_activation` into Account activity. No new tabs. Unread = projected rows only |
| Backend | Deployed `app.py` + `employee_app_invitation.py` to `wathefni-orchestrator` · backup `production-pre-employee-app-activation-inbox-20260809T003705Z` |
| Mobile OTA | canary `428d1000-80cb-4f36-83d5-f399af1b85bf` · runtime 0.1.0 · **no native build** |
| Prove | `smoke-test-employee-app-activation-inbox.py` PASS · Aziz 20→1 visible activation · Talal shift inbox unchanged · health/ready 200 |
| Evidence | `ops/evidence/employee-app-activation-inbox-20260809T003705Z/` |
| Verdict | **PASS** |

---

## 20260809T002100Z — Home: restore prior layout + blue Request leave (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Restored pre-polish Home exactly (pink workday, yellow tasks, sparse taller hero, white shift chip, serif Your tasks, tasks→leave→destinations). Only change: Request leave uses composition soft blue `#A9C0E4` with ink label |
| Channel | Canary OTA `356d5bb4-04f5-4040-b6ec-92e4a6413381` · runtime `0.1.0` · no native build |
| Rollback | `477496f3-be49-4dfe-af1b-c1c663566cbf` |
| Gates | colour 63 · density 93 · capability GREEN · `tsc` clean |
| Verdict | Stopped for owner Home review |

---

## 20260809T001400Z — Home polish: yellow hero / pink task / black CTA rhythm (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Home visual-only. Butter yellow workday with surface eyebrow (no white chip), compact when no shift, smaller calendar mark; pink compact action; YOUR TASKS as quiet eyebrow; Documents cream+green tile only; black Request leave last above nav. Cream intentional; no filler |
| Channel | Canary OTA `477496f3-be49-4dfe-af1b-c1c663566cbf` · runtime `0.1.0` · no native build |
| Rollback | `40218e48-1b3a-47b4-b2d3-5e9fb63b1560` |
| Gates | colour 61 · density 94 · capability GREEN · `tsc` clean |
| Verdict | Stopped for owner Home review |

---

## 20260809T000500Z — Home: pink workday / yellow tasks / olive Request leave (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Home palette roles: workday hero pink, Your tasks yellow, Request leave olive fill with ink label (not black, not white-on-olive). Placement unchanged in the action cluster. Schedule ambient follows pink with the workday role |
| Channel | Canary OTA `40218e48-1b3a-47b4-b2d3-5e9fb63b1560` · runtime `0.1.0` · no native build |
| Rollback | `479d905d-c1f4-41ba-bf98-91e09cfedb28` |
| Gates | colour 61 · density 93 · capability GREEN · `tsc` clean |
| Verdict | Stopped for owner Home review |

---

## 20260808T235500Z — Home: sparse-day taller hero + roomier rhythm (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Home-only. Quiet days (≤1 waiting surface, no discovery rows) grow the yellow workday card and open section gaps so cream below reads as designed margin. Busy days stay compact. No invented filler, no flexGrow footer |
| Channel | Canary OTA `479d905d-c1f4-41ba-bf98-91e09cfedb28` · runtime `0.1.0` · no native build |
| Rollback | `da5913a8-d67e-4d76-93d8-884515c772a7` |
| Gates | colour 59 · density 93 · capability GREEN · `tsc` clean |
| Verdict | Stopped for owner Home review |

---

## 20260808T235200Z — Home: action cluster (tasks → Request leave → quiet Documents) (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Home-only. Reordered so Request leave sits in the action cluster right after Your tasks (no flexGrow footer). Documents stays a quiet cream link and is omitted when the pink priority already opens documents/onboarding work |
| Channel | Canary OTA `da5913a8-d67e-4d76-93d8-884515c772a7` · runtime `0.1.0` · no native build |
| Rollback | `f8ab3b99-03c4-4ef7-9314-ba98d68ff89f` |
| Gates | colour 59 · density 92 · capability GREEN · `tsc` clean |
| Verdict | Stopped for owner Home review |

---

## 20260808T234300Z — Home: lightweight workspace link; sole black pill (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Home-only. Removed the green outer Documents card and the single-item “Your workspace” heading. Documents is now a cream-ground navigation link with a small green tile. Request Leave is the page’s only full-width pill and uses `flexGrow` + auto margin to sit near the tab bar while still scrolling under narrow / large-text conditions |
| Channel | Canary OTA `f8ab3b99-03c4-4ef7-9314-ba98d68ff89f` · runtime `0.1.0` · no native build |
| Rollback | `31a3807c-3e5f-4231-bd34-076ea52101c2` |
| Gates | colour 59 · density 91 · capability GREEN · `tsc` + lint clean |
| Verdict | Stopped for owner Home review |

---

## 20260808T233500Z — Home: bottom black Request Leave pill restored (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Home-only. Request Leave restored as full-width black pill below workspace / above nav (screenshot direction). Removed mid-page paired leave tile. Pink task stays under Your tasks; Documents is green AmbientCard so pink does not repeat. Section gap `xl`; attendance as two-line stack; synthetic name strip hardened |
| Channel | Canary OTA `31a3807c-3e5f-4231-bd34-076ea52101c2` · runtime `0.1.0` · no native build |
| Rollback | `22805669-b737-484c-b59f-b38f7a1f0550` |
| Gates | colour 59 · density 91 · capability GREEN · `tsc` clean |
| Verdict | Stopped for owner Home review |

---

## 20260808T232400Z — Home premium palette + compact black CTA (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Home-only. Preserved compact hierarchy; tuned yellow `#F0D065`, pink `#E5A6CB`, green `#B8CE7F`; Request Leave restored to a compact black CTA per latest owner direction; task gained balanced cream action orb; workspace became one intentional green destination surface; no geometry or extra sections |
| Hero | 26pt workday headline below the page title; 34pt two-tone calendar tile; softer divider; no nested card and no extra no-shift height |
| Channel | Canary OTA `22805669-b737-484c-b59f-b38f7a1f0550` · runtime `0.1.0` · no native build |
| Rollback | `6b2eb372-aec7-4289-be14-b16dc2366d04` |
| Gates | colour 59 · density 92 · capability GREEN · `tsc` + lint clean |
| Verdict | Stopped for owner Home review — other screens untouched |

---

## 20260808T231500Z — Home composition: blue Request Leave + compact actions (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Home-only. Request Leave black → composition blue (`homeComposition.requestLeave`, not module ambient). Action tiles compacted (horizontal, no 116pt min height). Hero tightened. Documents = cream destination card with green accent. No At a glance — `/app/home` lacks leave balance / next shift; unread is the bell; docs/onboarding already own pink |
| Rhythm | cream → yellow → pink + blue → cream/green accent → black nav |
| Channel | Canary OTA `6b2eb372-aec7-4289-be14-b16dc2366d04` · runtime `0.1.0` · no native build |
| Rollback | `cc2350c6-7845-4840-bc19-bb6a6b501d62` |
| Gates | colour 65 · density 91 · capability GREEN · `tsc` clean |
| Verdict | Stopped for owner Home review — other screens untouched |

---

## 20260808T230500Z — Home question-first rebuild; bento reverted (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Home-only. Bento abandoned on owner physical review (Request leave below the fold, nested white attendance card, oversized empty hero, arbitrary pink/green pairing, 30-day attendance stat, repeated green). Rebuilt around workday → waiting-on-me → what I can do now |
| Composition | Compact yellow workday (no nested card, inline attendance line) · black Request leave + pink action-required paired above the fold, stacking under `width < 360` or `fontScale ≥ 1.3` · secondary tasks as rows · destinations as compact rows with a small green accent · unread badge purple → ink |
| Not shipped | "At a glance" facts — `/app/home` exposes no leave balance and no next shift beyond today; unread already lives in the bell. Nothing invented to fill the row |
| Channel | Canary OTA `cc2350c6-7845-4840-bc19-bb6a6b501d62` · runtime `0.1.0` · no native build |
| Rollback | `e08e116d-8a2d-4a34-8a50-0be6992010cd` (bento) · `449d7910-4d8f-46c6-86d7-0772085dcb00` (pre-bento polish) |
| Gates | colour 59 · density 90 · capability GREEN · `tsc --noEmit` clean |
| Verdict | Stopped for owner Home review — visual system still not extended to other screens |

---

## 20260808T225500Z — Home adaptive bento / asymmetric priority (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Home-only: asymmetric yellow hero, role-based pink/green priority pair, adaptive workspace bento (1–4), no invented leave balances, no geometry, Request leave CTA kept |
| Channel | Canary OTA `e08e116d-8a2d-4a34-8a50-0be6992010cd` · runtime `0.1.0` · no native build |
| Rollback | `449d7910-4d8f-46c6-86d7-0772085dcb00` |
| Gates | color + density + capability + `tsc` PASS |
| Verdict | Stopped for owner Home review — do not extend to other pages yet |

---

## 20260808T224613Z — Home polish: butter / rose / pistachio + softer cards (canary OTA)

| Field | Value |
| --- | --- |
| Scope | Home-only visual refine: richer yellow/pink/green, rounder soft cards, shared cream action orbs, spacing rhythm; no geometry; greeting + “Today at work” kept |
| Channel | Canary OTA `449d7910-4d8f-46c6-86d7-0772085dcb00` · runtime `0.1.0` · no native build |
| Rollback | `8a929873-c3ca-46a3-a064-c4fc2e8bf860` |
| Gates | `verify-color-system` + `verify-density-hierarchy` + `tsc --noEmit` PASS |
| Verdict | Internal ship for device review — owner taste still open on Home before extending app-wide |

---

## 20260808T192633Z — Employee App Final Phase: Physical Visual QA (BLOCKED — not started)

- **No physical QA was performed.** No visual, RTL, Dynamic Type, VoiceOver or responsiveness
  verdict is claimed for any screen. Recorded so the absence of a report is not read as a pass.
- **Blocker 1 — stale build:** Visual A+B, C+D and E exist only in the local working tree
  (96 uncommitted files in the mobile app, plus `app.py`). Never committed, built, or published
  to `canary`. Whatever the device is running predates this work.
- **Blocker 2 — backend not deployed:** probed `https://api.wathefni.ai` directly —
  `/app/me`, `/app/leave`, `/app/home` return 401 (route exists), `/app/leave/duration` returns
  **404 (route absent)**. Two of Phase E's six additions could not appear on device even with
  an OTA published.
- **Blocker 3 — environment:** no `eas-cli` and not authenticated (cannot publish an OTA or
  read the installed update ID); no Xcode and zero iOS simulators (cannot render for inspection);
  no device.
- **Required sequence:** commit A–E → deploy backend (duration route must return 401, not 404)
  → publish OTA to `canary` (JS-only across A–E; no native module added, so OTA suffices while
  the installed native runtime is still `0.1.0`) → install, force-quit, relaunch → confirm build
  block → run checklist. Steps 1–3 need owner credentials.
- **Prepared:** consolidated A–E device checklist covering build confirmation, Phase E additions,
  navigation, density, composition shapes A–F, long content, AR/RTL double-flip watch, Dynamic
  Type AX3/AX5, VoiceOver, and real-device interactions. Ready to run, not run.
- **Committed (blocker 1 cleared):** `cf26d59..1e77bf6`, 11 commits. Backend `c80900c`; mobile split
  by subsystem across 10 commits (colour system · layout/list primitives · composition+navigation ·
  device lock · API contract+formatting · employee screens · EN/AR · gates · native module+OTA
  config · docs/evidence). Phase-based commits were not reconstructible: A–E and Phases 0–4 touched
  the same files with no intermediate commit, so the boundary exists only in the transcripts.
  Employee App tree now clean; the repo's remaining 2354-file backlog was left untouched.
  Typecheck clean and all gates green at the tip.
- **Verified against production:** deployed `/opt/wathefni/orchestrator/app.py` pulled and diffed —
  128 lines in 5 hunks differ, all Phase E. The 18k-line git diff was archival lag already live,
  so the backend deploy ships only the Phase E delta.
- **Evidence:** `ops/evidence/employee-app-physical-qa-phaseF-20260808T192633Z/`
- **Verdict:** **BLOCKED** · `EMPLOYEE_APP_READY_FOR_OWNER_FREEZE=NO` (cannot be assessed)

---

## 20260808T191537Z — Employee App Visual Refinement Phase E: high-value employee additions (PASS, static + behavioural)

- **Scope:** Request Leave balance + requested duration, manager contact, Inbox relative time,
  payslip year grouping verification, document expiry task copy. Last product refinement phase
  before physical iPhone visual qualification.
- **Regression fixed (pre-existing, live):** `/app/leave` emits `current_balance`; the mobile
  contract declared `balance_days`, a field the API has never sent. Every leave type rendered a
  confident **"0 days available"** wherever balances were enabled. Contract corrected to the real
  field names; a missing number now renders as nothing, and a genuine `0` still renders.
- **Backend (read-only, no authority):** `GET /app/leave/duration` — composes the create path's own
  primitives (`get_leave_policy` → `holiday_dates_for_range` → `chargeable_leave_days`) so it cannot
  disagree with what a submitted request is charged; writes nothing; gated on `leave/request`.
  `/app/home` `tasks[].detail` — the soonest renewal's `document_type` / `label` / `expiry_date`,
  passed through from compliance rows Home already loaded and previously discarded.
- **Never invented:** balance absent → silent · duration `available: false` → no line · expiry
  unparseable → generic label · manager number not dialable → no call button.
- **Navigation:** unchanged from Phase C+D — `Home · Schedule · Leave · Payslips · Profile`,
  Inbox as Home-header bell, Documents via Home/tasks/routes, `employeeAppComposition.ts` canonical.
- **Employee number:** raw `employee_key` **not** restored. `employee_persons.employee_number` exists
  in the Wave 2 hub but is not joined into `/app/profile`; reported as a domain-model gap.
- **Prove:** mobile behavioural 23/23 · mobile static 79/79 · backend 34/34 · 11 prior suites green ·
  typecheck clean · EN/AR parity · iOS bundle exported clean (3.24 MB).
- **Local limitation:** `smoke-test-leave-guardrails.py` imports `app.py` → needs `psycopg2`
  (not installed locally). Pre-existing, unrelated; runs on staging.
- **Evidence:** `ops/evidence/employee-app-visual-phaseE-20260808T191537Z/`
- **Owner decisions open:** WhatsApp-to-manager alongside call · copy for `available` vs
  `current_balance` once reservations are enabled.
- **Verdict:** **PASS** · `PHYSICAL_VISUAL_QA_READY=YES` · physical iPhone review not started

---

## 20260808T102214Z — Employee App Visual Refinement Phase C+D: density, hierarchy & navigation (PASS, static)

- **Scope:** Home hierarchy, bottom-navigation simplification, shared compact list primitive,
  Documents / Inbox / Leave / Payslips / Bank / Onboarding / Profile density, restraint pass,
  long-history scalability. No backend, entitlement or authority change; no new features.
- **Navigation:** tabs are Home · Schedule · Leave · Payslips · Profile. Inbox left the tab bar
  for an unread bell in the Home header; canonical route is now `/notifications`
  (`INBOX_ROUTE`), with `/(tabs)/notifications` kept as an explicit alias so links already in
  flight still land on the Inbox. Payslips took the freed slot. Unentitled tabs are removed,
  not disabled. `employeeAppComposition.ts` remains the only composition system.
- **Duplication removed on Home:** Leave destination card (tab + request button remain),
  Schedule destination card, inbox strip, onboarding task beside the onboarding progress card.
  The rule lives in the contract: `homeDestinations = homeTiles − TABBED_MODULE_SURFACES`.
- **Density:** new `src/components/lists.tsx` (`ListRow`, `SectionHeader`, `ShowMoreButton`,
  `usePagedList`), modelled on Schedule's `RecordedRow`. Cards now only mark action-required,
  current state, or a problem. Bank stopped printing the same masked IBAN under three
  headings; Onboarding collapsed two progress surfaces into one and names HR-owned items
  instead of counting them; Profile states name and job title once.
- **Scalability:** Documents and Payslip history group by year, keep only the newest year
  open, and page inside a year (10 / 12). Inbox partitions unread / earlier / account
  activity, pages at 15, and never demotes unread. Leave pages at 12. Proven against a
  264-document, 11-year fixture. Schedule's capped history unchanged.
- **Gates:** 343 PASS / 0 FAIL. New: density+hierarchy behavioural (24) and static scan (71).
  Updated for the moved route rather than worked around: composition shapes (54 → 61),
  push follow-through, capability foundation. A+B colour and a11y gates still green.
  iOS bundle exports clean (1368 modules).
- **Evidence:** `ops/evidence/employee-app-visual-phaseCD-20260808T102214Z/`
- **Verdict:** **PASS (static + behavioural)** — physical-device qualification not started;
  next phase not started; Employee App not frozen.

---

## 20260808T094952Z — Employee App Visual Refinement Phase A+B: trust, terminology, layout & colour system (PASS, static)

- **Scope:** employee-facing copy sweep (EN+AR), payslip payment-date defect, shared layout
  tokens + canonical page shell, tab-bar/safe-area correctness, responsive text, Dynamic Type
  ceilings, final colour system with brand/semantic role separation. No backend, entitlement
  or authority change; no IA restructure.
- **Defect fixed:** payslip detail printed `Payment date: Not available` unconditionally
  because it never read `payslip.payment_date`. Now reads the field and omits the row when
  payroll has not dated the payslip.
- **Colour:** 22 tokens → 18; `successSoft`/`dangerSoft`/`warningSoft`/`accentSoft`/`chip`/
  `skeleton` retired. Closest ambient↔semantic pair moved from dE 1.7 to dE 54.6. All ink and
  muted-text pairings AA for body text (4.5:1 – 17.0:1).
- **Safe area:** tab bar sized `60 + insets.bottom`; screens read the measured bar height via
  `BottomTabBarHeightContext`, no per-page magic numbers. `@react-navigation/bottom-tabs`
  promoted to an explicit `~6.5.7` dependency.
- **New gate:** `scripts/verify-color-system.py` (32 checks) — contrast, role separation, no
  index-based colour, no untokenised colour literals.
- **Prove:** typecheck 0 · colour 32/32 · capability foundation GREEN · a11y+i18n 21/21 ·
  session/refresh 8/8 · composition 54/54 · documents hierarchy 7/7 · feature copy 9/9 ·
  push follow-through 14/14 · pin crypto PASS · EN/AR parity 580==580
- **Evidence:** `ops/evidence/employee-app-visual-phaseAB-20260808T094952Z/`
- **Owner:** physical iPhone review pending — see `PHYSICAL_QA_CHECKLIST.md` (bottom-tab
  clearance on SE + home-indicator devices, AX3/AX5, AR/RTL, VoiceOver, low-brightness
  `surface`-on-`bg` legibility)
- **Verdict:** **PASS at static/gate level** — physical not claimed · Density/Hierarchy phase
  **not started** · Employee App **not frozen**

## 20260808T074820Z — Employee App P1 Phase 4: final functional qualification (PASS)

| Field | Value |
|---|---|
| Scope | Push tap follow-through via Phase 1 registry · FeatureUnavailable `features.reason` customer copy · global state / session-refresh re-proof · EN/AR/RTL + code-level a11y completion · OTA canary · physical QA checklist |
| Backend | `build_employee_push_data` enriches Expo push `data` with safe in-app path hints · `outbound_delivery` threads variables into push |
| Mobile | `resolvePushDestination` + signed-in tap follow-through · FeatureUnavailable reason i18n · Access/Error a11y · new gates (push / feature-copy / session-refresh / a11y-i18n scan) |
| Frozen | Home · Schedule · Auth 0–5 · Bank ESS · Payslip release/PDF · Documents legitimacy · **no Auth Phase 6 · no Employee App freeze · no HR App · no visual redesign** |
| Prove | Local 16/0 · production 13/0 · push follow-through 14 · feature-copy 9 · session-refresh 8 · a11y-i18n 21 · capability foundation GREEN |
| OTA | group `f9fc3c25-f535-40e0-b273-ef3214da93c2` · iOS `019fe05a-a586-7410-8198-b0b9f79b6167` · runtime `0.1.0` · rollback `905477b6-1db1-4b6b-b0c8-bcc72bb32c3a` · Aziz/Talal canary only |
| Verdict | **`PASS`** · **`FUNCTIONAL_READY_FOR_PHYSICAL_VISUAL_QA = YES`** |
| Stamp | `ops/evidence/employee-app-p1-phase4-20260808T074820Z/` |
| Next | Dedicated **Physical Visual QA & Responsiveness** with owner review on device. Do not freeze yet. |

---

## 20260808T073000Z — Employee App P1 Phase 3: surface refinement (PASS)

| Field | Value |
|---|---|
| Scope | Profile personal/employment hierarchy · Documents attention/current/history · Payslips list/detail polish · Inbox/Settings presentation · EN/AR/RTL/a11y baseline on touched surfaces |
| Backend | `/app/profile` adds `personal` + `employment` over the same employee row · manager only when stored · `/app/me` stays compact |
| Mobile | Profile/Documents feature views · Bank only under Profile · Settings device-security retry · payslip earnings/deductions grouping · Inbox unread/earlier + VoiceOver labels |
| Frozen | Home · Schedule · Auth 0–5 · Bank ESS · Payslip release/PDF rules · Documents legitimacy · no Auth Phase 6 |
| Prove | Local 13/0 · production 13/0 · profile projection · documents hierarchy 7/7 · Phase 0–2 regressions green · payslips P0 savepoint flake fixed |
| Verdict | **`PASS`** (internal wave step) |
| Stamp | `ops/evidence/employee-app-p1-phase3-20260808T073000Z/` |
| Next | Phase 4 — Inbox/Settings completion, global states, RTL/a11y finish, functional + physical visual qualification. **No freeze yet. No owner review yet.** |

---

## 20260808T070113Z — Employee App P1 Phase 2: unified read-only Schedule (PASS)

| Field | Value |
|---|---|
| Scope | `/app/workday` read-only projection over the existing Shifts + Attendance authorities · one Schedule tab replacing the split Shifts and Attendance screens |
| Authority | **Creates none.** No employee clocking, no attendance correction, no payroll effect · every value is the owning module's stored value · `read_only` block returned to the client |
| Backend | `_module_read` (renamed from `_home_module_read`, now surface-labelled) · `_employee_shift_rows` / `_employee_attendance_rows` gained opt-in `detailed`; `/app/shifts/*` and `/app/attendance` shapes unchanged |
| Mobile | `app/(tabs)/schedule.tsx` + `src/features/schedule/ScheduleView.tsx` · deleted `app/(tabs)/shifts.tsx`, `app/attendance.tsx`, `ShiftsView`, `AttendanceView` · tab + Home tile on **either** entitlement |
| Routing | `RouteSpec.feature` accepts a tuple for combined destinations · `/shifts`, `/(tabs)/shifts`, `/attendance` are explicit aliases so older builds and in-flight notifications land on the new surface |
| Honesty | Per-authority `disabled`/`error`/`ready` · a failed read carries no value and does not take its sibling down · "No shift scheduled today" only when Shifts was actually read · Kuwait wall-clock times via `formatClockTime` |
| Prove | Local 12/0 · production 12/0 · new workday contract 33/33 on synthetic production fixtures (Aziz/Talal untouched) · EN+AR keysets match |
| Deploy | `app.py` sha256 `347b2f40…0246ba` — local and host identical · health 200 |
| Verdict | **`PASS`** (internal wave step) |
| Stamp | `ops/evidence/employee-app-p1-phase2-20260808T070113Z/` |
| Next | Phase 3 surface refinement. **No owner review yet** — wave not complete. |

---

## 20260808T062710Z — Employee App P1 Phase 1: server-owned Home + strict links (PASS)

| Field | Value |
|---|---|
| Scope | `/app/home` server-owned task/read projection · simplified Home hierarchy · strict client route registry |
| Backend | Single query per fact via shared module read helpers · per-module savepoint so one failed read cannot abort the projection · tasks derived by owning modules, never re-derived from status strings |
| Mobile | Home reads one endpoint instead of five · one launcher (destinations), no duplicate quick actions · `APP_ROUTES` registry replaces substring path matching |
| Prove | Local 12/0 · production 11/0 · home projection contract green |
| Verdict | **`PASS`** (internal wave step) |
| Stamp | `ops/evidence/employee-app-p1-phase1-20260808T062710Z/` |

---

## 20260808T055747Z — Employee App P1 Phase 0: P0 stabilization (PASS)

| Field | Value |
|---|---|
| Scope | Runtime `app_access_enabled` enforcement · deploy-time reconcile migration under advisory lock · mobile typecheck clean · Home false-empty states removed · source-neutral payslip authority copy · payslip cache cleanup · auto-lock diagnostics build-gated |
| Gate | New `ops/employee-app-p1-release-gate.sh` — local / prod-db / staging-db classes, prints PARTIAL rather than PASS when a class is skipped |
| Prove | Local 12/0 · production 11/0 · several stale pre-existing assertions corrected (payslips shipped, harness app-access grant, Kuwaiti phone fixtures) |
| Verdict | **`PASS`** (internal wave step) |
| Stamp | `ops/evidence/employee-app-p1-phase0-20260808T055747Z/` |

---

## 20260807T205203Z — Employee Payslips P0.1: Official PDF (PASS)

| Field | Value |
|---|---|
| Scope | Official employee PDF from immutable external-authority payslip snapshot · replace `.txt` download |
| Eligibility | `external_import` + `money_authority=external` · native preview never official |
| Backend | `payroll_payslip_official_pdf` v1.0.0 · wave3 v1.2.0 · private workspace storage · audited download |
| Mobile OTA | canary `905477b6-1db1-4b6b-b0c8-bcc72bb32c3a` · runtime 0.1.0 · **no native build** |
| Prove | Smoke 52/0 PASS · sample PDFs in evidence · amounts match API · EN/AR · peer/replace/revoke |
| Production blocker | External is mirror only · payment_processing disabled · no payment_date · Wave3 synthetic-only — do not fake native authority |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/employee-payslips-p0_1-20260807T205203Z/` |
| Next | **Do not start Employee App P1 or Auth Wave 2 Phase 6.** |

---

## 20260807T203541Z — Employee Payslips P0: HR Release Gate + Employee Read-Only (PASS)

| Field | Value |
|---|---|
| Scope | Explicit employee release on payroll payslips · self-scoped `/app/payslips` · mobile Payslips UX · module gate · notify |
| Authority | `status=active AND employee_visibility=released` · period never implies visibility |
| Backend | `payroll_payslip_wave3` v1.1.0 + release DDL · HR release/unrelease · employee list/detail/download |
| Dashboard | `PostHire-C4jIRIa-.js` — employee visibility + Release/Withdraw |
| Mobile OTA | canary `7fb336c2-7454-4537-a11f-e36457c61571` · runtime 0.1.0 · **no native build** |
| Prove | Smoke 85/0 PASS · draft invisible · release self-only · peer 404 · revoke/replace · idempotent · module-off · EN/AR |
| Download honesty | Statement `.txt` only · `official_document=false` · no `payment_date` |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/employee-payslips-p0-20260807T203541Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-payslips-p0-20260807T202829Z/ROLLBACK.sh` |
| Next | **Do not start Auth Wave 2 Phase 6.** Official PDF blocked until authoritative document + payment_date exist. |

---

## 20260807T191930Z — Employee App access eligibility + invite trigger (PASS)

| Field | Value |
|---|---|
| Scope | Company Employee App on/off · employee `app_access_enabled` · invite only on explicit enable · migration/create never invite |
| Contract | `employee_app_access_eligibility_v1` |
| Design | `ops/EMPLOYEE_APP_ACCESS_ELIGIBILITY.md` |
| Backend | `employee_app_access.py` · invitation gates · create/onboarding auto-invite removed |
| Dashboard | `PostHire-BpOFfS5m.js` — Enable access & invite / Disable eligibility |
| Prove | Eligibility matrix PASS · invitation smoke PASS |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/employee-app-access-eligibility-20260807T191930Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-app-access-eligibility-20260807T191930Z/ROLLBACK.sh` |
| Next | **Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T185259Z — Migration & Sync P6.1 Live UI Refresh (PASS)

| Field | Value |
|---|---|
| Scope | Post-sync / review / lifecycle live soft-refresh · no full reload · dirty-safe · no new realtime platform |
| Design | `ops/EMPLOYEE_MIGRATION_SYNC_P6_1_LIVE_UI_REFRESH.md` |
| Dashboard | `PostHire-B84Q_9SB.js` — CustomEvent + BroadcastChannel + 30s visibility-gated soft poll |
| Backend | Unchanged (P1–P6 frozen) |
| Prove | Bundle needles · source contract · sync→list refresh sources · P6/P5.2/P1 smokes |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/employee-migration-sync-p6.1-20260807T185259Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p6_1-20260807T185259Z/ROLLBACK.sh` |
| Next | **Stop.** Do not auto-start further Migration & Sync phases. Do not start Auth Wave 2 Phase 6. |

---

## 20260807T183857Z — Migration & Sync P6 leavers + lifecycle (PASS)

| Field | Value |
|---|---|
| Scope | Lifecycle signals → policy (review/auto/ignore) → hub active/left · Auth Wave 2 revoke · rehire · Needs Review · no hard-delete |
| Contract | `employee_migration_sync_p6_leavers` @ `6.0.0` |
| Design | `ops/EMPLOYEE_MIGRATION_SYNC_P6_LEAVERS.md` |
| Backend | `employee_migration_lifecycle.py` · connectors sync_run wiring · lifecycle approve/reject APIs |
| Dashboard | lifecycle cards in Needs review |
| Smokes | P6 PASS · P5.2–P1 PASS |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/employee-migration-sync-p6-20260807T183857Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p6-20260807T183857Z/ROLLBACK.sh` |
| Next | **Stop.** Do not auto-start further Migration & Sync phases. Do not start Auth Wave 2 Phase 6. |

---

## 20260807T181334Z — Migration & Sync P5.2 connector secret hardening (PASS)

| Field | Value |
|---|---|
| Scope | Fail-closed Fernet seal/unseal · remove plainhex fallback · remediate existing insecure canary secrets · scheduler rejects unreadable secrets |
| Contract | `employee_migration_sync_p5_2_secret_hardening` @ `5.2.0` |
| Design | `ops/EMPLOYEE_MIGRATION_SYNC_P5_2_SECRET_HARDENING.md` |
| Backend | `employee_migration_connectors.py` secret seal path · remediation · scheduler mailbox key EnvironmentFile |
| Smokes | P5.2 PASS · P5.1–P1 PASS |
| Remediation | 2 plainhex → Fernet resealed; 0 require re-entry |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/employee-migration-sync-p5.2-20260807T181334Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p5_2-20260807T181334Z/ROLLBACK.sh` |
| Next | Freeze Connected Systems when ready. **Do not start P6 or Auth Wave 2 Phase 6.** |

---

## 20260807T104900Z — Migration & Sync P5.1 scheduler + real SFTP (PASS)

| Field | Value |
|---|---|
| Scope | Production scheduler (`next_sync_at` · locking · backoff · missed-run recovery) · real `sftp` file-feed connector · CSV/XLSX · sha256 ledger · same P1–P4 foundation apply path |
| Contract | `employee_migration_sync_p5_1_scheduler_sftp` @ `5.1.0` |
| Design | `ops/EMPLOYEE_MIGRATION_SYNC_P5_1_SCHEDULER_SFTP.md` |
| Backend | `employee_migration_sftp.py` · connectors scheduler · `migration-connector-scheduler-worker.py` · systemd timer |
| Dashboard | `PostHire-B2-S5cGs.js` — status · schedule · last/next sync · Pause/Resume · Sync now |
| Smokes | P5.1 PASS · P5–P1 PASS |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/employee-migration-sync-p5.1-20260807T104900Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p5_1-20260807T104900Z/ROLLBACK.sh` |
| Next | Customer vendor API only when required (`api_stub` stays). **Do not start P6 or Auth Wave 2 Phase 6.** |

---

## 20260807T102912Z — Migration & Sync P5 Connected Systems (PASS)

| Field | Value |
|---|---|
| Scope | Real Connected systems tab · connector contract · sync runs · deterministic canary · incremental watermark · pause/resume/disconnect · secrets sealed · feeds P1–P4 foundation pipeline |
| Contract | `employee_migration_sync_p5_connectors` @ `5.0.0` |
| Design | `ops/EMPLOYEE_MIGRATION_SYNC_P5_CONNECTORS.md` |
| Backend | `employee_migration_connectors.py` · foundation honesty · connected-systems APIs |
| Dashboard | `PostHire-D9_dugHt.js` — connect / run sync / pause / disconnect / sync history |
| Smokes | P5 PASS · P4–P1 PASS |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/employee-migration-sync-p5-20260807T102912Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p5-20260807T102912Z/ROLLBACK.sh` |
| Next | P6 leavers when requested. **Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T101417Z — Migration & Sync P4 opening balances + current-state cutover (PASS)

| Field | Value |
|---|---|
| Scope | Leave opening ledger adjustment · payroll draft/staging (masked, never effective) · compliance unverified · current assignment + shift planning metadata · missing≠zero · native wins · idempotent |
| Contract | `employee_migration_sync_p4_cutover` @ `4.0.0` |
| Design | `ops/EMPLOYEE_MIGRATION_SYNC_P4_CUTOVER.md` |
| Backend | `employee_migration_cutover.py` · field-model/foundation hooks |
| Dashboard | `PostHire-XWDMcYyG.js` — P3 onboarding labels + P4 opening/current preview lines |
| Smokes | P4 PASS · P3 PASS · P2 PASS · P1 foundation PASS |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/employee-migration-sync-p4-20260807T101417Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p4-20260807T101417Z/ROLLBACK.sh` |
| Next | P5 done (`20260807T102912Z`). **Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T095819Z — Migration & Sync P3 existing-employee onboarding migration (PASS)

| Field | Value |
|---|---|
| Scope | Honest onboarding dispositions (external / history / N/A / needs Wathefni / unknown) · no fake completion · preview labels · native activity wins · idempotent re-import · safe rollback |
| Contract | `employee_migration_sync_p3_onboarding` @ `3.0.0` |
| Design | `ops/EMPLOYEE_MIGRATION_SYNC_P3_ONBOARDING.md` |
| Backend | `employee_migration_onboarding.py` · foundation apply path · completion recompute guard · schema ledger savepoint fix |
| Dashboard | Migration Sync preview “Onboarding · {label}” (shipped live with P4 `PostHire-XWDMcYyG.js`) |
| Smokes | P3 PASS · P2 PASS · P1 foundation PASS on prod (`WATHEFNI_SCHEMA_APPLY=1`) |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/employee-migration-sync-p3-20260807T095819Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p3-20260807T095819Z/ROLLBACK.sh` |
| Next | P4 done (`20260807T101417Z`). **Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T093314Z — Migration & Sync P2 field model + deep records (PASS)

| Field | Value |
|---|---|
| Scope | 3-layer field model (canonical · company custom · raw source payload) · reusable mapping profiles · deep import (identity staged, contacts, bank proposed-only, docs/compliance evidence) |
| Contract | `employee_migration_sync_p2_field_model` @ `2.0.0` |
| Design | `ops/EMPLOYEE_MIGRATION_SYNC_FIELD_MODEL.md` |
| Backend | `employee_migration_field_model.py` · foundation parse/preview/commit/rollback · mapping suggest/save APIs |
| Dashboard | Migration Sync field-mapping panel (EN) |
| Smokes | foundation smoke PASS · `OK employee migration sync P2 field model` on prod |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/employee-migration-sync-p2-20260807T093314Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p2-20260807T093314Z/ROLLBACK.sh` |
| Next | P3 done (`20260807T095819Z`). **Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T085406Z — Migration & Sync P1 foundation-only production path (PASS)

| Field | Value |
|---|---|
| Scope | Kill legacy import fallback that could seed compliance; foundation is sole production migration path; reject `start_onboarding=true` |
| Contract | `employee_migration_sync_p1_foundation_only` @ `1.2.0` |
| Backend | `employee_migration_foundation.py` · `app.py` import handler |
| Plan | `ops/EMPLOYEE_MIGRATION_SYNC_EXPANSION.md` |
| Smokes | `OK employee migration foundation local smoke` · `OK employee migration sync P1 production-safe gate` on prod |
| Gates | 422 `migration_onboarding_forbidden` · 503 `migration_foundation_required` · no `seed_compliance` in import handler |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/employee-migration-sync-p1-20260807T085406Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-sync-p1-20260807T085406Z/ROLLBACK.sh` |
| Next | P2 deep records when requested. **Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T083709Z — Bank ESS P2 production workflow (PASS)

| Field | Value |
|---|---|
| Scope | P2: upload→extract→confirm/correct→proposed→HR→payroll→Apply · failure UX · HR extracted fields · evidence re-link |
| P1 | Frozen (MIME sniff + HR masking preserved) |
| Backend | `employee_bank_ess.py` · `app.py` · contract `bank_ess_v1_p2_production_workflow` |
| Dashboard | Extracted-from-certificate panel EN+AR |
| Mobile OTA | canary `a61e1f11-469e-41b7-9bb9-2078c682e82b` |
| Prove | P2 **4/4 + 19/19** with real Gulf Bank PDF · Aziz FP `0f349ce848ab5e4b` |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/bank-ess-p2-production-workflow-20260807T083709Z/` |
| Next | Optional physical EN/AR soak. **Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T081338Z — Bank ESS P1 real-document extraction qual (PASS)

| Field | Value |
|---|---|
| Scope | Real Gulf Bank IBAN letter PDF (`1786090542147.pdf`) OCR prove before P2 |
| Fixes | MIME sniff for extensionless evidence paths · HR extraction IBAN masking |
| Prove | Bank/holder/IBAN+validation/account/branch/SWIFT · confidence · confirm/correct · private evidence · non-authoritative · HR compare · effective unchanged · Aziz FP `0f349ce848ab5e4b` |
| Verdict | **`PASS`** (currency SKIP — not on letter) |
| Stamp | `ops/evidence/bank-ess-p1-real-doc-extraction-qual-20260807T081338Z/` |
| Next | Ready for Bank ESS P2 when requested. **Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T080230Z — Bank ESS P1 document-first KW certificate OCR (PASS)

| Field | Value |
|---|---|
| Scope | P1 only: document-first upload · Kuwait/GCC Mistral extraction · confirm/correct · manual fallback · evidence link · HR extraction summary · authority preserved |
| Backend | `employee_bank_ess.py` · `app.py` · `kuwait_gcc_document_intelligence/{schemas,intake,extraction}.py` |
| Flags | `WATHEFNI_BANK_ESS_OCR_V1=on` · companies `WATHEFNI` |
| Contract | `ops/BANK_ESS_AND_ONBOARDING_COMPLETION_CONTRACT.md` (`bank_ess_v1_p1_document_first`) |
| Dashboard | BankReviewPanel extraction status EN+AR |
| Mobile OTA | canary `95d11ede-9516-4d85-bc73-936167b83fa3` |
| Prove | P1 focused **8/8 + 12/12** · Qual Bank ESS **51/51** · onboarding **31/31** · Aziz FP unchanged `0f349ce848ab5e4b` |
| Migrations | Additive `employee_bank_evidence.extraction_*` only |
| Verdict | **`PASS`** (residual: real IBAN-letter OCR field richness not live-proven on synthetic PDF) |
| Stamp | `ops/evidence/bank-ess-p1-document-first-20260807T080230Z/` |
| Next | Optional physical Aziz/Talal certificate walk. **Do not start P2. Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T074024Z — Bank ESS P0 verified-at-HR (PASS)

| Field | Value |
|---|---|
| Scope | P0 only: HR approve=verified · Apply=effective · state/copy · withdraw onboarding sync · needs_review recovery · KW IBAN at submit · Profile/Settings Bank entry · dual-control preserved |
| Backend | `employee_bank_ess.py` · `employee_selfservice_wave5.py` · `app.py` |
| Contract | `ops/BANK_ESS_AND_ONBOARDING_COMPLETION_CONTRACT.md` |
| Dashboard | Bank review labels/copy EN+AR |
| Mobile OTA | canary `d73cd3c7-703e-4d66-a865-90d90b925125` |
| Prove | Qual Bank ESS **47/47** · onboarding **31/31** · Aziz effective FP unchanged `0f349ce848ab5e4b` |
| Migrations | None |
| Verdict | **`PASS`** |
| Stamp | `ops/evidence/bank-ess-p0-verified-at-hr-20260807T074024Z/` |
| Next | P1 / document OCR not started. **Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T063432Z — Invitation/delivery physical acceptance (PASS w/ residuals)

| Field | Value |
|---|---|
| Scope | HR EN+AR needles · states · Resend/Re-invite · code exception gating · Aziz emailed-code activate → session reopen · HR activated · no pending duplicates |
| Prove | `canary-prod-employee-app-invitation-physical.py` PASS · live activate/refresh PASS · copy vitest 4/4 · PIN crypto PASS |
| Residuals | On-device PIN/Face ID UI (no USB) · headless profile-card screenshot incomplete (bundle+API cover copy) |
| Verdict | **`PASS`** (with residuals) |
| Stamp | `ops/evidence/employee-app-invitation-physical-20260807T063432Z/` |
| Next | Optional owner glance at Aziz App access EN/AR. **Do not start Auth Wave 2 Phase 6.** |

---

## 20260807T061923Z — Employee app invitation + delivery (PASS canary)

| Field | Value |
|---|---|
| Scope | Long-term invitation/delivery (separate from Auth Wave 2): auto-invite · email/WhatsApp deliver · HR status · Resend/Re-invite without code · exception code handoff only |
| Contract | `ops/EMPLOYEE_APP_INVITATION_DELIVERY_CONTRACT.md` |
| Backend | `employee_app_invitation.py` · create/onboarding hooks · dashboard `/app-invitation*` · outbound `company_code` fix on WhatsApp session |
| Flags | `WATHEFNI_EMPLOYEE_APP_AUTO_INVITE=on` · `WATHEFNI_EMPLOYEE_APP_AUTO_INVITE_COMPANIES=WATHEFNI` |
| Dashboard | App access invitation status + Resend/Re-invite (no normal code) |
| Prove | Smoke PASS · Aziz live reinvite **delivered via email** · no code disclosure · Phase 6 not started |
| Verdict | **`PASS`** (canary) — optional physical HR EN/AR UI walk |
| Stamp | `ops/evidence/employee-app-invitation-delivery-20260807T061923Z/` |
| Next | Continue continuous wave. **Do not start Auth Wave 2 Phase 6.** |

---

## 20260806T230823Z — Auth Wave 2 Phase 2 Face ID gating fix (PARTIAL)

| Field | Value |
|---|---|
| Finding | Opt-in skipped after PIN · reopen PIN-only |
| Fix | Relax usable (hardware+enrolled) · one-time boot recovery offer · OTA `aec3862c-70b5-47d3-9a2e-d7f07eade52b` |
| Verdict | **`partially proven`** — confirm Face ID offer + unlock on device |
| Stamp | `ops/evidence/auth-wave2-phase2-biometric-fix-20260806T230823Z/` |

---

## 20260806T230037Z — Auth Wave 2 Phase 2 Face ID / Touch ID (PARTIAL)

| Field | Value |
|---|---|
| Scope | Optional Face ID/Touch ID after PIN · auto prompt on reopen · PIN fallback · Settings toggle · canary Aziz/Talal |
| Native | iOS `24c71b0a-6b09-4bb3-8d0d-c1e5dcbdc076` (build 10) · Android `e7eefb47-abfb-4b0e-8387-bf02b75805cc` (vc 3) |
| Channel | Canary OTA `02919c30-f663-4471-a8a6-058dbdf37054` · PIN=1 · BIOMETRIC=1 |
| Prove | Bio unit 34/34 · PIN 38/38 · hardening 28/28 · live preserve 10/10 |
| Restore | Aziz code **321898** · phone `99338566` |
| Verdict | **`partially proven`** — install native → OTA → physical Face ID matrix |
| Stamp | `ops/evidence/auth-wave2-phase2-biometric-20260806T230037Z/` |
| Next | Owner device qualify. **Stop — no Phase 3.** |

---

## 20260806T225101Z — Auth Wave 2 Phase 1 session-hardening (PARTIAL)

| Field | Value |
|---|---|
| Scope | Stop random “Session expired” · central `classifyAuthFailure` · wipe only after definitive refresh reject / stale epoch / inactive / logout · soft keep on network/5xx/language |
| Channel | Canary OTA `41239180-9b5a-4cc1-88f7-7a2f8d2ad7f8` · PIN=1 · biometric=0 |
| Prove | Hardening unit 28/28 · PIN unit 38/38 · Wave1 live 30/30 |
| Verdict | **`partially proven`** — owner device matrix (force-quit / offline / EN↔AR / PIN / logout / revoke) |
| Stamp | `ops/evidence/auth-wave2-phase1-session-hardening-20260806T225101Z/` |
| Next | Force-quit → pull OTA → confirm no spurious OTP. Biometrics stay off until this closes. |

---

## 20260806T223109Z — Auth Wave 2 Phase 1 seamless EN↔AR (PARTIAL)

| Field | Value |
|---|---|
| Scope | Remove language restart Alert · silent RTL reload · cover to avoid flash · keep session/PIN preserve |
| Channel | Canary OTA `7a0d99fc-0e0e-44be-8b9f-5cc4ad9c8b20` |
| Prove | Unit 37/37 · Wave1/Bank 30/30 |
| Verdict | **`partially proven`** — owner EN→AR→EN once, then fully proven |
| Stamp | `ops/evidence/auth-wave2-phase1-pin-20260806T223109Z/` |
| Next | Force-quit → OTA → Settings EN↔AR (no dialog). No Phase 2. |

---

## 20260806T222232Z — Auth Wave 2 Phase 1 locale restart session wipe fix (PARTIAL)

| Field | Value |
|---|---|
| Finding | After RTL restart Alert, `/me` failure → `clearLocalAuthMaterial` → Session expired → OTP |
| Fix | Preserve marker · never wipe on locale restart · fall back to PIN lock not activation |
| Channel | Canary OTA `9dc373a9-b9ce-4a7a-9877-5023454ecdc3` |
| Restore | Aziz activation code **692269** issued |
| Prove | Unit 37/37 · Wave1/Bank live 30/30 |
| Verdict | **`partially proven`** — physical EN↔AR/AR↔EN after restore |
| Stamp | `ops/evidence/auth-wave2-phase1-pin-20260806T222232Z/` |

---

## 20260806T221706Z — Auth Wave 2 Phase 1 RTL language restart fix (PARTIAL)

| Field | Value |
|---|---|
| Finding | EN→AR used silent `DevSettings.reload` after `forceRTL` — looked like a crash |
| Fix | Confirm Alert · `Updates.reloadAsync` · one-shot unlocked session resume (no OTP/PIN) |
| Channel | Canary OTA `173506a4-e2ea-4a66-9d1e-d5b2860c426c` · no native build |
| Prove | Unit 34/34 · Wave1+Bank live 30/30 · Bank/onboarding unchanged |
| Verdict | **`partially proven`** — confirm Alert + resume once on device |
| Stamp | `ops/evidence/auth-wave2-phase1-pin-20260806T221706Z/` |
| Next | Force-quit → OTA → Settings EN↔AR · no biometrics |

---

## 20260806T215837Z — Auth Wave 2 Phase 1 local PIN (PARTIAL)

| Field | Value |
|---|---|
| Scope | Local 6-digit PIN create/unlock/change · 5-fail → OTP · Aziz/Talal canary · flag `EXPO_PUBLIC_LOCAL_PIN_UNLOCK` |
| Channel | Canary OTA group `b41cdbcf-9338-4073-a0be-af8ea9773c71` · runtime 0.1.0 · **no native build** |
| Prove | Unit 29/29 · crypto PASS · capability GREEN · Wave 1 live 30/30 · Bank/onboarding unchanged |
| Verdict | **`partially proven`** — physical force-quit/PIN soak pending on Aziz/Talal devices |
| Stamp | `ops/evidence/auth-wave2-phase1-pin-20260806T215837Z/` |
| Next | Owner: force-quit → OTA → OTP→PIN→unlock→5-fail→Change PIN · EN/AR. Do **not** start biometrics. |

---

## 20260806T214259Z — Auth Wave 2 Phase 0 Wave 1 freeze (READY_FOR_PHASE_1)

| Field | Value |
|---|---|
| Scope | Freeze OTP activate / request-code / refresh / logout / new-device revoke / Kuwait aliases / session_epoch / SecureStore — no PIN |
| Tests | Unit **35/35** · live Aziz+Talal **30/30** · bank/onboarding snapshots unchanged |
| Verdict | **`ready_for_phase_1`** — Phase 1 not started |
| Stamp | `ops/evidence/auth-wave1-freeze-20260806T214259Z/` · contract `ops/AUTH_WAVE1_FROZEN_CONTRACT.md` |
| Next | Wait for explicit Phase 1 authorization |

---

## 20260806T213600Z — Auth Wave 2 readiness reassessment (READY)

| Field | Value |
|---|---|
| Scope | Reassess Auth Wave 2 after real-bank acceptance; no auth code |
| Gates | Bank ESS + onboarding fully proven · withdrawn cannot resurface · EN/AR/mobile · permissions/tenant/idempotency/migration/payroll green |
| Verdict | **`ready`** — Phase 1 = local PIN unlock only (biometrics / idle / recovery / device trust deferred) |
| Stamp | `ops/AUTH_WAVE2_READINESS_DECISION.md` · evidence `ops/evidence/aziz-real-bank-acceptance-20260806T212710Z/` |
| Next | Owner may authorize Phase 1 implementation; do not start Phase 2+ |

---

## 20260806T212710Z — Aziz real bank acceptance (PASS)

| Field | Value |
|---|---|
| Scope | Read-only acceptance after real submit → HR → payroll → Apply |
| Live truth | Verified Gulf bank / ABDULAZIZ HAMAD RASHED ALMULLA / last4 **9548** · onboarding **completed** 4/4 · absent from queue · surfaces agree · reconcile `changed: false` |
| Defect found | Stale walkthrough `withdrawn` still projected as Bank submission; fixed with bank-of-record cutoff |
| Channel | Backend projection only (no mobile OTA) |
| Verdict | **`ACCEPTANCE_PASS`** 19/19 |
| Stamp | `ops/evidence/aziz-real-bank-acceptance-20260806T212710Z/` |
| Next | Auth Wave 2 remains blocked |

---

## 20260806T193736Z — Correction resubmit 409 + field-error UX (DEPLOYED)

| Field | Value |
|---|---|
| Live finding | Physical resubmit POST `/app/bank/requests` → **409** `bank_request_already_active` on request `d65628a4…` (`needs_information`); IBAN fixture valid; mobile showed generic error |
| Fix | Replace sealed proposal on `needs_information`/`draft` and return to `pending_hr` · field-level validation errors · preserve form · busy/idempotency lock |
| Channel | Backend + canary OTA group `e3d3ffae-14a8-42f9-bc87-301763b0b0cd` · iOS `019fd894-c5e9-7601-bbd2-edaf8618f7d9` · Android `019fd894-c5e9-7d94-88d5-7a7b36f3aff5` |
| Prove | `RESUBMIT_REPLACE_PROOF_PASS` — same request_id, `needs_information → pending_hr`, display IBAN last4 `0000` |
| Verdict | **`deployed`** — continue Phase 2 HR review of Aziz’s corrected request |
| Stamp | `ops/evidence/bank-ess-phase2-resubmit-ux-20260806T193628Z/` |
| Next | Aziz force-quit/reopen → Bank shows under review; HR Approve → Payroll → Apply. Auth Wave 2 blocked. |

---

## 20260806T192823Z — Returned-state submitted date patch (DEPLOYED)

| Field | Value |
|---|---|
| Scope | Returned/resubmitted Bank screen: compose `Submitted on` + real date in code; strip leftover `{date}`/`{{date}}` from `bank.submittedAt` |
| Channel | Canary OTA group `f4f7a2d6-da32-45b6-a08c-4669e66701d4` · iOS `019fd88c-567c-7be3-af0f-c8e5a4db24fc` · Android `019fd88c-567c-7ef6-b58a-491a29ecb163` · full rebuild (iOS 1303 modules) |
| Verdict | **`deployed`** — force-quit/reopen then confirm date; use synthetic IBAN `KW30TEST0000000000000000000000` for resubmit |
| Stamp | `ops/evidence/bank-ess-phase2-approval-date-validation-20260806T191329Z/mobile/` |

---

## 20260806T191329Z — Bank approval stages + date + validation correction (DEPLOYED)

| Field | Value |
|---|---|
| Scope | Distinguish HR approval → payroll approval → apply · concurrency guard + in-memory duplicate lock · render submitted date without placeholder interpolation · enforce registry-based IBAN/account format + checksum validation |
| Audit finding | First click succeeded `pending_hr → pending_payroll`; second click succeeded `pending_payroll → approved`; neither click applied |
| Remediation | Invalid approved Aziz request `d65628a4…` returned through audited `approved → needs_information`; no invalid value became payroll-effective |
| Channel | Backend enforcement + dashboard `PostHire-BOf-Lh9g.js` + canary OTA group `f77228cd-af7d-4235-9c08-4392f019addc` · iOS `019fd880-8f4f-77d3-9934-5674e5c217b3` · Android `019fd880-8f4f-7580-b129-c6f251eac274` |
| Qualification | Dashboard Vitest 24/24 + build PASS · mobile typecheck + capability GREEN · malformed KW/generic identifiers rejected · health 200 · remediation audit verified |
| Verdict | **`deployed`** — continue the same Phase 2 with Aziz correcting/resubmitting a valid IBAN |
| Stamp | `ops/evidence/bank-ess-phase2-approval-date-validation-20260806T191329Z/` |
| Next | Aziz force-quit/reopen, verify real submitted date + correction reason, resubmit valid IBAN; HR verifies distinct HR/payroll/apply stages. Auth Wave 2 remains blocked. |

---

## 20260806T185624Z — HR onboarding drawer visual correction (DEPLOYED)

| Field | Value |
|---|---|
| Scope | Remove always-expanded Bank panel · compact Bank row under Needs HR · open canonical review only from **Review bank** · drawer-safe single-column values |
| Channel | Dashboard-only `PostHire-C_o12y1w.js` · no backend/OTA change |
| Qualification | Focused Vitest 21/21 · build PASS · 1,134 controls / 0 dead · live asset 200 |
| Verdict | **`deployed`** — continue the same Phase 2 review |
| Stamp | `ops/evidence/bank-ess-hr-drawer-cleanup-20260806T185624Z/` |
| Next | Hard-refresh dashboard; open Aziz → Needs HR action → Review bank |

---

## 20260806T184542Z — HR onboarding drawer Bank review + clarity (DEPLOYED · continue Phase 2)

| Field | Value |
|---|---|
| Scope | Wire `BankReviewPanel` into onboarding drawer · ownership groups (Needs HR / Waiting on employee / payroll-other / Completed) · compact rows + View details · bank checklist sync from ESS · fix mobile `Submitted on {{date}}` |
| Channel | Dashboard `PostHire-CUJvv77p.js` · backend reconcile/sync · OTA `59ec9dc5-2ffb-4018-b64c-788f3bb94b31` |
| Prove | Aziz bank `processing` + `being_reviewed` + `review_bank` · completion `waiting_on_hr` |
| Verdict | **`deployed`** — continue Phase 2 HR Approve/Reject/Apply walk |
| Stamp | `ops/evidence/bank-ess-hr-drawer-phase2-20260806T184542Z/` |
| Next | Hard-refresh dashboard + mobile OTA · Auth Wave 2 still blocked |

---

## 20260806T182313Z — Temporary Aziz Bank ESS allowlist for physical form test (DEPLOYED)

| Field | Value |
|---|---|
| Scope | Add Aziz `WATHEFNI-96599338566` to Bank ESS + ESS bank real allowlists via temporary systemd drop-in (normal eligibility — no UI hardcode) |
| Channel | Backend env only · **no OTA** (tip remains `388e8cf5…`) |
| Prove | `/app/me` bank enabled · onboarding `open_bank` · `/app/bank` 200 · EN/AR OK |
| Cleanup | `ops/evidence/bank-ess-aziz-temp-allowlist-20260806T182313Z/cleanup/REMOVE_AZIZ_AFTER_PHASE2.sh` **after Phase 2** |
| Verdict | **`deployed`** — awaiting Aziz physical Bank form walk |
| Stamp | `ops/evidence/bank-ess-aziz-temp-allowlist-20260806T182313Z/` |
| Next | Aziz force-quit → Open bank → submit real form · Auth Wave 2 still blocked |

---

## 20260806T181405Z — Bank ESS eligibility align me/onboarding/bank (DEPLOYED · physical walk pending)

| Field | Value |
|---|---|
| Scope | Same canonical Bank ESS eligibility for `/app/me`, `/app/onboarding` (`open_bank` only when eligible), `/app/bank`; mobile CTA + route gated; Aziz stays allowlist-disabled (no hardcode) |
| Channel | Backend production + JS OTA `canary` `0.1.0` group `388e8cf5-1d6b-4140-9c84-bfff55504928` · iOS `019fd849-26c1-72ec-94b8-500e667e3bc0` |
| Prove | Live matrix PASS: Aziz ineligible (no `open_bank`, bank 403) · synthetic `7001` eligible (open_bank + bank 200) · EN/AR onboarding 200 |
| Capability | GREEN · export fingerprint includes syncLayoutLocale guard + bank gates |
| Verdict | **`deployed`** — physical force-quit/reopen walk still needed on canary iPhone |
| Stamp | `ops/evidence/bank-ess-eligibility-align-20260806T173727Z/` |
| Rollback | OTA → prior tip `85f648c9-73a0-4b14-9d8e-838913496a4d` · backend `app.py.bak-bank-elig*` |
| Next | Owner physical: no Open bank CTA for Aziz · no fresh-start crash · then continue Phase 1 soak (Auth Wave 2 still blocked) |

---

## 20260806T154352Z — Phase 1 clean Bank/completion UI deploy (BLOCKED)

| Field | Value |
|---|---|
| Scope | Clean deploy of Bank ESS + onboarding-completion UI only (no full lifecycle qual, no Auth Wave 2) |
| Attempt | Release branch `release/bank-ess-ui-20260806T154352Z` · worktree from HEAD · VPS apps overlay · contract check OK |
| Blocker | Live PostHire source not recoverable without OCR regression **or** shipping dirty WIP (`MigrationSyncShell` / Leave / Shifts / soft-keep not in live bundle) |
| Prod change | **None** — dashboard SHA unchanged `PostHire-6LCFY5pA` · health 200 · no OTA |
| Verdict | **`blocked`** |
| Stamp | `ops/evidence/bank-ess-ui-clean-deploy-20260806T154352Z/` |
| Next | Freeze PostHire source matching live OCR bundle, then surgical bank/completion patch + deploy |

---

## 20260806T153212Z — Bank ESS + onboarding completion UI (DONE · Auth Wave 2 still blocked)

| Field | Value |
|---|---|
| Scope | Employee `/bank` screen · canonical completion on checklist · HR `BankReviewPanel` + `OnboardingCompletionStrip` · sealed proposals / three-layer authority already live on backend |
| Channel | Backend already canary-deployed · UI locally built + contract-qualified · **no** production dashboard rsync / OTA this stamp (tree has unrelated WIP) |
| Backend matrix | Bank ESS **43/43** · Onboarding **27/27** (`qual-20260806T052441Z`) |
| UI quals | Mobile capability foundation GREEN · dashboard Vitest 451 PASS · build PASS |
| Verdicts | Bank ESS **partially proven** · Onboarding completion **partially proven** · Auth Wave 2 **blocked** |
| Residual | Clean UI deploy + Aziz/Talal EN/AR live walk required before `fully proven` / Auth unblock |
| Stamp | `ops/evidence/bank-ess-onboarding-completion-20260806T052304Z/` · readiness `ops/AUTH_WAVE2_READINESS_DECISION.md` |
| Next | Clean deploy of bank/completion UI only → live canary walk → re-stamp |

---

## 20260806T035255Z — HR OCR summary UI + docs wave close (DONE · Bank ESS next)

| Field | Value |
|---|---|
| Scope | Shared `DocumentExtractionSummary` on Compliance + Onboarding · mask document numbers · extracted vs verified · Civil ID F/B + pair · no auto-overwrite · six-type live HTTP re-qual |
| Channel | Dashboard dist `/var/www/wathefni-dashboard` + orchestrator journey/OCR enrich · canary DocVal/lifecycle unchanged · HARD off |
| Verdicts | All six document types **fully proven** incl. `hr_ocr_summary_ui` · civil SHA unchanged · canaries cleaned |
| Residual | Real-world OCR accuracy needs continued sampling · Bank ESS still open · Auth Wave 2 blocked until Bank ESS + onboarding complete |
| Stamp | `ops/evidence/hr-ocr-summary-ui-20260806T035255Z/` |
| Next | Bank ESS |

---

## 20260806T033827Z — Kuwait docs live-HTTP qualification matrix (DONE · Bank ESS still open)

| Field | Value |
|---|---|
| Scope | Full disposable-canary matrix: Civil ID F+B, passport, residence, work permit, employment contract, personal photo · HR projection + approve/reject/replace · OCR schemas · never touch real Civil ID |
| Channel | Live uvicorn HTTP only (no TestClient) · minted Aziz session · per-type subprocess isolation · timeouts/retries/partials |
| Verdicts | All six **partially proven** (shared: HR OCR summary UI hidden; Civil ID also identity_matching partial). None missing/broken after WP/contract fixture rerun |
| Civil ID | SHA `fe98f7d9…` accepted unchanged · canary leftovers 0 |
| Smokes | `smoke-test-onboarding-civil-id-dual-side.py` OK · uvicorn `/docs`+`/openapi.json` 200 |
| Stamp | `ops/evidence/kuwait-docs-qual-matrix-20260806T033827Z/` |
| Residual | Bank ESS separate · HR OCR UI not shown · do not claim mobile onboarding complete |

---

## 20260806T20260806T020012Z — Dual-side Front upload 500 fix (READY for phone retest)

| Field | Value |
|---|---|
| Root cause | OCR `date`/`datetime` not JSON-serializable on `attach_part` / lifecycle meta |
| Fix | `_json_ready` + lifecycle meta sanitize · deployed |
| Prove | Front upload smoke HTTP 200 · canary reset pending · civil_id SHA unchanged |
| Stamp | `ops/evidence/civil-id-dual-side-front-500-fix-20260806T020012Z/` |

---

## 20260806T015133Z — Civil ID dual-side disposable canary LIVE (READY for mobile front/back test)

| Field | Value |
|---|---|
| Scope | Prod deploy dual-side · flags Aziz-only · create `civil_id_dual_side_canary` · real Civil ID untouched · canary OTA Front/Back UX |
| Channel | Backend + JS OTA `canary` `0.1.0` group `968adf2a-135f-4cae-b4cc-7136f74628de` |
| Proven | Canary in `your_actions` with `upload_front`/`upload_back` · civil_id accepted sha `fe98f7d9…` unchanged · legacy_single |
| Stamp | `ops/evidence/civil-id-dual-side-canary-live-20260806T015133Z/READY.md` |
| Owner | Force-close app → Onboarding → CANARY front then back live test |

---

## 20260806T014717Z — Civil ID front+back dual-side (IMPLEMENTED · canary prove pending deploy)

| Field | Value |
|---|---|
| Scope | One `civil_id` item · Front/Back parts on one draft attempt · pair gate · same-version HR promote · disposable `civil_id_dual_side_canary` · Aziz accepted Civil ID untouched · DocVal soft · HARD=off · no native scanner |
| Channel | Backend flags + employee mobile OTA + HR web dual preview |
| Smokes | `smoke-test-onboarding-civil-id-dual-side.py` PASS |
| Stamp / evidence | `ops/evidence/civil-id-dual-side-20260806T014717Z/` · `ops/CIVIL_ID_DUAL_SIDE.md` |
| Owner review | After live disposable-canary prove; do not enable real Civil ID replacement demand until soak |

### Residual update
- Pre-GA residual #2 (Proper Civil ID front-and-back) → **in progress / behind flags** (prove on disposable canary first)

---

## 20260806T004945Z — Kuwait onboarding wave CLOSE + DocVal canary cleanup (DONE)

| Field | Value |
|---|---|
| Scope | Close current Kuwait onboarding wave · stamp baseline · remove disposable `civil_id_canary_test` only · preserve real Civil ID · keep lifecycle+DocVal soft canary Aziz/Talal · HARD off · no GA · native scanner deferred · Auth Wave 2 audit/plan only |
| Channel | Backend-only cleanup + docs stamp |
| Smokes | `ops-aziz-docval-canary-item.py cleanup` · real `civil_id` accepted sha `fe98f7d9…` unchanged · flags SOFT=on HARD=off LIFECYCLE=on |
| Stamp / evidence | `ops/evidence/kuwait-onboarding-wave-close-20260806T004945Z/` · Auth plan `ops/AUTHENTICATION_WAVE2_AUDIT_AND_PLAN.md` |
| Owner review | Onboarding wave closed; Auth Wave 2 awaits approval before code |

### DocVal canary close outcomes
- Clear frame-filling Civil ID accepted (crop FP fixed)
- Random non-document rejected with correct wrong-document copy
- No raw errors
- Disposable canary item removed

### Pre-GA residuals (recorded)
1. Bank-details submission in employee app
2. Proper Civil ID front-and-back handling
3. Qualify passport / residence / work permit / employment contract / personal-photo DocVal flows
4. Controlled rollout beyond canary
5. Native document scanner — deferred until end

---

## 20260805T231332Z — DocVal Try again reopens picker (DONE — ready for owner smoke)

| Field | Value |
|---|---|
| Scope | Blocked upload Try again → new file picker · never resend rejected file · calm EN/AR preserved |
| Channel | JS-only OTA canary `0.1.0` · group `18b27224-09d0-4fcf-b6da-cd91e28c21bf` · iOS `019fd434-8846-742c-9f4d-066d8beb4359` |
| Smokes | Typecheck PASS · no same-file retry static check · Aziz canary item reset + VERIFY PASS |
| Stamp / evidence | `ops/evidence/docval-try-again-picker-ota-20260805T231332Z/` |
| Owner review | Force-close/reopen → mismatch → Try again → choose different file |

---

## 20260805T230300Z — Aziz disposable Civil ID canary item (READY FOR LIVE DOCVAL TEST)

| Field | Value |
|---|---|
| Scope | Optional `civil_id_canary_test` for Aziz only · real civil_id accepted preserved · soft-gate aliased to Civil ID · reset/cleanup scripts |
| Channel | Backend only (no OTA/native) |
| Smokes | `ops-aziz-docval-canary-item.py verify` PASS · visible `your_actions` + upload · civil_id hash unchanged |
| Stamp / evidence | `ops/evidence/aziz-docval-canary-item-*/` |
| Cleanup | `ops-aziz-docval-canary-item.py cleanup` |
| Owner review | Pull-to-refresh Onboarding; test mismatch → uncertain → reset → correct |

---

## 20260805T224917Z — Document Validation Parity mobile UX OTA (DONE — ready for owner live review)

| Field | Value |
|---|---|
| Scope | EN/AR mismatch + unclear correction alerts · uncertain→HR advisory · no raw 422/codes · Wave 2A preview/history/resubmit preserved |
| Channel | JS-only OTA `canary` runtime `0.1.0` · group `b6bccf66-d7a2-4b95-b5dd-73543f9faa86` · iOS update `019fd41e-4220-751f-b5d5-72f427cc48c5` |
| Smokes | Typecheck PASS · OTA published current · calm UX smoke PASS · soft allowlist Aziz+Talal · prod doc-validation smoke OK |
| Stamp / evidence | `ops/evidence/onboarding-doc-validation-parity-ota-20260805T224917Z/` |
| Rollback | `eas update:rollback b6bccf66-d7a2-4b95-b5dd-73543f9faa86` |
| Owner review | **Requested** — force-close/reopen; three upload scenarios below |

---

## 20260805T224005Z — Interaction assurance program open (P0/P1 closed)

| Field | Value |
|---|---|
| Scope | Close confirmed interaction-audit P0/P1 · retain residual register · synthetic IAX fixture env for 495 unproven · Vitest 13 drift fixes · calendar calm-error wave start · release gate fails only on confirmed P0/P1 |
| Channel | Docs + harness + dashboard test contracts; production IAX batch-0 fixture create/cleanup; no employee OTA required |
| Smokes | Release gate GO (0 confirmed P0/P1 blockers; 495 unproven tracked) · 7/7 previously red Vitest files green (44 tests) · calendar calm envelope unit check · production IAX canary 11/11 |
| Stamp / evidence | `ops/INTERACTION_ASSURANCE_PROGRAM/` · `ops/evidence/interaction-assurance-20260805T224005Z/` · audit `ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/` |
| Rollback | Prior audit `deploy/ROLLBACK.sh` unchanged; IAX canary is disposable-fixture only |
| Owner review | Not required; residual 495 is a tracked assurance program, not a product latch |

---

## 20260805T220256Z — Interaction authority late closure (DONE)

| Field | Value |
|---|---|
| Scope | Onboarding upload capability gate · account-deletion capability/idempotency · notification/leave repeat locks and feedback · Documents/Settings back controls |
| Channel | JS-only OTA to internal `canary` + production backend/dashboard authority fixes; no native build required |
| Smokes | Typecheck + capability foundation GREEN · iOS export pass · Talal `/app/me` capability proof pass · production account-deletion replay reused one task · 3-role attendance read/manage probe 6/6 |
| Stamp / evidence | `ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/` · late deployment `20260805T220256Z` · OTA group `34a288bc-36c6-40fb-80e3-a38fe5449320` |
| Rollback | `ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/deploy/ROLLBACK.sh` (backend/dashboard/gateway + OTA-to-embedded) |
| Owner review | Not required; bundled into the completed major interaction-audit wave |

---

## 20260805T195406Z — Full interaction and dead-control audit (DONE)

| Field | Value |
|---|---|
| Scope | Employee app static controls · capability/deep-link gates · session refresh · self-scope reads · notification/leave/push/sign-out repeat safety |
| Channel | Production-connected WATHEFNI canary · backend/dashboard deploy · no native dependency change |
| Smokes | 1,101 source controls / 0 dead · 240 dashboard role/locale/viewport pages + 24 final targeted pages · 191 mutation probes / 0 server failures · 17/17 employee API controls pass · P0/P1 confirmed broken = 0 |
| Stamp / evidence | `ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/` |
| Rollback | `ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/deploy/ROLLBACK.sh` |
| Owner review | Not required; no new native build or employee-app UX wave |

---

## 20260805T150828Z — EMF manager resolution fix (DONE)

| Field | Value |
|---|---|
| Scope | `manager_phone` parse/resolve · unresolved non-blocking warning · exception CSV · commit manager_employee_key · preview ID/manager detail |
| Channel | Backend canary WATHEFNI |
| Smokes | Manager smoke OK · exact fixture preview OK · user batch `5f09ba60` left previewed |
| Stamp / evidence | `ops/evidence/employee-migration-foundation-manager-20260805T150828Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-emf-manager-20260805T150828Z/ROLLBACK.sh` |
| Owner review | Re-preview test file; do not confirm `5f09ba60` until Unknown Manager shows warning |

---

## 20260805T144609Z — Employee Migration Foundation P0–P2 (DONE)

| Field | Value |
|---|---|
| Scope | Roster import batch ledger · row results · exception CSV · idempotent replay · source_mappings · Wave4 manager_phone fix · create-only/no-message |
| Channel | Backend canary (`WATHEFNI`) + dashboard import UX totals/exceptions |
| Smokes | `OK employee migration foundation local smoke` on prod |
| Stamp / evidence | `ops/evidence/employee-migration-foundation-p0p2-20260805T144609Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-employee-migration-foundation-20260805T144609Z/ROLLBACK.sh` |
| Owner review | Not required for P0–P2; import stays create-only |

---

## 20260805T142303Z — Document Validation Parity soft-gate (DONE — ready for owner live review)

| Field | Value |
|---|---|
| Scope | `/app` upload classify/verify/quality/identity/expiry · soft block clear mismatches · uncertain→HR · Wave 2A untouched |
| Channel | Backend canary + mobile JS correction UX (OTA/next build) |
| Smokes | Doc-validation parity OK · Wave 2A OK · health active |
| Stamp / evidence | `ops/evidence/onboarding-doc-validation-parity-20260805T142303Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-onboarding-doc-validation-20260805T142303Z/ROLLBACK.sh` |
| Owner review | **Requested** — Civil ID / passport / contract / certs / photo on Aziz+Talal; hard-gate still off |

---

## 20260805T134124Z — HR Onboarding Web canary correction (DONE — ready for owner live review)

| Field | Value |
|---|---|
| Scope | HR projection + lifecycle writers · manage gates · drawer/portal menu · primary action consistency |
| Channel | Backend + dashboard web deploy |
| Smokes | `CANARY_QUAL_OK` · Wave 2A local smoke on prod · owner mutate + viewer 403 |
| Stamp / evidence | `ops/evidence/hr-onboarding-web-canary-20260805T134124Z/` |
| Rollback | `/opt/wathefni/backups/production-pre-hr-onboarding-web-canary-20260805T134124Z/ROLLBACK.sh` |
| Owner review | **Requested** — live review Onboarding page (owner + restricted HR) |

---

## 20260805T114246Z — Wave 2A final cleanup (DONE — ready for owner live review)

| Field | Value |
|---|---|
| Scope | Global RTL/LTR · hide Expo headers · hide dormant optionals · rejection reason once · lifecycle states preserved |
| Backend | `onboarding_lifecycle_wave2a.py` canary deploy |
| Backup | `/opt/wathefni/backups/production-pre-onboarding-wave2a-cleanup-20260805T114246Z` |
| Smokes | `AZIZ_SMOKE_OK` · `EN_AR_API_SMOKE_OK` |
| Native build | iOS #7 internal — https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/78a25dd7-0731-4e27-95fe-f7f44b532c51 |
| Activation | phone `99338566` · code `356216` |
| Rollback | flag off · restore bak · prior IPA build 6 |
| Evidence | `ops/evidence/employee-onboarding-wave2a-cleanup-20260805T114246Z/` |
| Owner review | **Requested** — Wave 2A complete; next work continues as Wave 3+ without per-feature installs |

---

## Template (copy for next ship)

```
## YYYYMMDDTHHMMSSZ — <wave> / <short title>

| Field | Value |
|---|---|
| Scope | |
| Channel | OTA \| native build \| backend-only |
| Smokes | |
| Stamp / evidence | |
| Rollback | |
| Owner review | not yet \| requested \| passed |
```

| 2026-08-06 | DocVal decision-order | Soft canary Aziz/Talal | Non-doc message wins over capture copy; blurry+high OCR blocks; idempotent bypass after reset closed | Stamp `ops/evidence/docval-decision-order-20260806T001109Z/` · canary reset pending |

| 2026-08-06 | DocVal crop FP fix | Soft canary Aziz/Talal | crop_hot_sides demoted to weak signal; frame-fill clear ID allows; rejection audit keeps capture_quality | Stamp `ops/evidence/docval-crop-false-positive-fix-20260806T003126Z/` · canary reset pending |

## 20260806T155845Z — Phase 1A Bank ESS UI source recovery (no deploy)

- **Verdict:** `ready_to_deploy`
- **Evidence:** `ops/evidence/bank-ess-ui-source-recovery-20260806T155845Z/`
- **Recovered baseline:** `4f435beda3ee36dfebcf28afd06f58f027268f1f` (artifact-proven vs live `PostHire-6LCFY5pA`, norm-byte-identical)
- **Release tip:** `6547a25883609cbe84ca2f25bb8b2ea24afedce6` on `release/bank-ess-ui-clean-20260806T155845Z`
- **Included:** BankReviewPanel, OnboardingCompletionStrip, employee bank/completion mobile surfaces + EN/AR
- **Excluded:** Migration Sync / Leave / Shifts / soft-keep WIP (not in baseline→release diff)
- **Build/tests:** dashboard vite build PASS; posthire Vitest 162/162; mobile capability GREEN; EN/AR bank keys PASS
- **Production:** unchanged (`PostHire-6LCFY5pA` SHA `406b9dca…`, health 200)
- **Auth Wave 2:** not started

## 20260806T170025Z — Phase 1B Bank ESS UI clean deploy (live)

- **Verdict:** `deployed`
- **Evidence:** `ops/evidence/bank-ess-ui-clean-deploy-live-20260806T170025Z/`
- **Dashboard:** `PostHire-BRA7Ln_S.js` SHA `e833ce5c…` (prev `PostHire-6LCFY5pA` backed up)
- **Mobile OTA:** canary group `326e2040-6603-4c34-a6db-1022ff8095a6` runtime `0.1.0` · iOS `019fd80f-3cc8-7905-8863-2c4cefed9e4b` · Android `019fd80f-3cc8-75bd-8b6e-d7cfed86c919`
- **Smokes:** live API 21/21 · OCR asset needles PASS · EN/AR bank+completion API PASS · device force-close pull pending owner
- **Phase 2 / Auth Wave 2:** not started

## 20260806T172002Z — Bank ESS OTA crash fix (syncLayoutLocale)

- **Verdict:** `deployed` (republished; physical force-close verify pending owner — no USB device on agent)
- **Evidence:** `ops/evidence/bank-ess-ota-crash-fix-20260806T172002Z/`
- **Rolled back:** `326e2040-6603-4c34-a6db-1022ff8095a6` → republish group `cb2655a4-6451-4724-b321-0d20929aa838` (prior cf26d59)
- **Root cause:** `_layout` called `syncLayoutLocale()` but stale recovered `i18n/index.tsx` lacked it → AppErrorBoundary “fresh start”
- **Fix OTA tip:** group `85f648c9-73a0-4b14-9d8e-838913496a4d` runtime `0.1.0` · iOS `019fd81a-629a-7289-82ce-6207924ecc10` · Android `019fd81a-629a-7922-95b0-f9a502cf1c4e`
- **Ignore:** intermediate `f65e46d0…` (stale Metro cache)
- **Smokes:** iOS/Android export PASS · startup contract PASS · capability GREEN · published fingerprint PASS
- **Owner:** force-quit + reopen → launch / Bank / Onboarding
- **Phase 2 / Auth Wave 2:** not started

## 20260806T200247Z — Onboarding: one canonical state + next action per surface

- **Verdict:** `deployed` · live Aziz/Talal walkthrough GREEN (physical device pull pending owner)
- **Evidence:** `ops/evidence/onboarding-completion-reconcile-20260806T200247Z/`
  (`prove/consistency-matrix.md`, `prove/live-walkthrough.txt`,
  `prove/reconcile-authority-smoke.txt`, `deploy/backend-shipped.diff`)
- **Root cause 1 — stale bank history outranked the bank of record:**
  `reconcile_onboarding_bank_item` ordered requests by recency only, so an older
  `rejected` request beat a newer `applied` one and every HR read reverted the
  bank item. Fixed by `desired_onboarding_bank_state` authority order:
  open request → live `employee_bank_effective` → terminal history. Idempotent.
- **Root cause 2 — each surface picked its own "next" item:** the queue and the
  drawer/app/profile ran separate selection loops over different item sets.
  Replaced by `select_next_item()` in the contract (required + open, class
  priority, unblocked-then-due tiebreak).
- **Root cause 3 — `reopened` hardcoded owner `employee`:** a bank change under
  review showed queue `hr` vs drawer/app/profile `employee`. `next_action()` now
  takes the owner from `current_actor()` (the snapshot's own buckets).
- **Root cause 4 — mobile preferred a local state→copy table** over the
  contract's message, so client copy could contradict the backend owner. Server
  message now wins; the per-state string is an offline fallback only.
- **Live matrix:** T0 applied → T1 submitted → T2 returned → T3 resubmitted →
  T4 HR approved → T5 payroll approved → T6 applied. All four surfaces identical
  at every step; one Apply satisfies bank and completes onboarding; drawer
  re-reads are stable. 46/46 walkthrough checks, 15/15 authority smoke, 0 HTTP
  errors (Talal's bank `403` is the expected ineligibility).
- **Backend:** `app.py` + `onboarding_completion_contract.py` — shipped diff is
  5 hunks, all next-item/next-action (`deploy/backend-shipped.diff`).
- **Dashboard:** `PostHire-Bcu7y5zK.js` live in `/var/www/wathefni-dashboard`
  (backup `/opt/wathefni/backups/dashboard-onboarding-ux-20260806T200247Z`).
- **Mobile OTA:** canary group `b540423a-de1a-44c9-afa5-caa9504d2957` runtime
  `0.1.0` · iOS `019fd8d1-10b2-745c-a768-3be2eddac34e` · Android
  `019fd8d1-10b2-771b-a7b6-547b5d99ca79` · prior group
  `e3d3ffae-14a8-42f9-bc87-301763b0b0cd` for republish rollback.
- **Rollback:** `ops/evidence/onboarding-completion-reconcile-20260806T200247Z/ROLLBACK.sh`
- **Owner:** force-quit + reopen the app → Onboarding (bank item under Completed,
  no HR/payroll clutter) and Bank.
- **Auth Wave 2:** still blocked.

## 20260806T205803Z — Controlled broad rollout (Bank ESS + onboarding completion)

- **Verdict:** `broad_rollout_go`
- **Evidence:** `ops/evidence/bank-ess-onboarding-broad-rollout-20260806T205803Z/`
- **Pre:** Aziz synthetic payroll bank cleared (no invented IBAN — `bank_details=pending` for real submit) · Talal `/app/bank` 403 · rollback artifacts usable · prior OTA group `e3d3ffae…` intact
- **Stage 1:** 6 real + 3 synthetic bank-enabled (Aziz/Fouad/Noura/Mariam/Fahad/Dana) · Talal denied · `ELIGIBILITY_OK`
- **Stage 2:** 13 real + 3 synthetic bank-enabled · employee app 17 keys (Talal app-only) · `ELIGIBILITY_OK`
- **Smoke:** consistency `SMOKE_OK` 7/7 · authority `RECONCILE_AUTHORITY_OK` 15/15
- **Monitor:** journal errors 0 · edge 200/200/200 · reconcile idempotent · expected 403s only
- **Preserved:** Auth Wave 2 blocked · Settings/setup WIP untouched · `pending_payroll→hr` ownership
- **Rollback:** `ops/evidence/bank-ess-onboarding-broad-rollout-20260806T205803Z/ROLLBACK.sh`
- **Owner:** Aziz should submit real bank details via Bank ESS (synthetic cleared)

## 20260806T211805Z — Aziz synthetic bank ghost cleared (API)

- **Verdict:** `fixed`
- **Evidence:** `ops/evidence/aziz-synthetic-bank-clear-20260806T211805Z/`
- **Root cause:** prior cleanup superseded effective + soft-deleted profile but left `employee_bank_verified`; `/app/bank` still projected Walkthrough as verified/approved
- **Fix:** `revoked_at` on verified · current reads ignore revoked · no bank-of-record ⇒ no terminal history projected · revoke 4 synthetic verified rows (audit retained)
- **Live API:** `has_verified_bank=false` · verified/payroll/submission null · `can_submit_new=true` · next step “Add your bank details…”
- **Owner:** force-quit → Bank → empty form → submit real details (no TEST IBAN)

## 20260806T232633Z — Auth Wave 2 Phase 3: Smart Auto-Lock

- **Verdict:** `partially_proven` (OTA + unit PASS; iOS/Android natives FINISHED; physical matrix open)
- **Evidence:** `ops/evidence/auth-wave2-phase3-autolock-20260806T232633Z/`
- **Scope:** background timeout · device-lock probe · Face ID/PIN unlock · Settings timeouts · EN/AR RTL · canary Aziz/Talal only
- **Policy:** default 30s · Immediate / 30s / 1m / 5m / Never · Never may be company-disabled · device-lock always locks when native probe works · never clears SecureStore/PIN · no Wave 1/OTP touch
- **OTA:** group `fda08e77-f7a1-464c-8596-00cc4e4c6461` runtime `0.1.0` · env PIN=1 BIOMETRIC=1 AUTO_LOCK=1 · prior rollback `3d4d10ca-…`
- **Native:** iOS `7b3dc831-…` build 11 · Android `92869701-…` vc 5 (vendored `modules/wathefni-screen-detector` after Expo 51 gradle fix)
- **Unit:** 39/39 `smoke-test-auth-wave2-phase3-autolock-unit.py`
- **Owner matrix:** bg&lt;30s no lock · bg≥30s Face ID/PIN · screen lock · Face ID cancel→PIN · success opens · no OTP · Bank/onboarding OK · EN/AR RTL
- **Phase 4:** not started

## 20260807T001856Z — Auth Wave 2 Phase 3 timeout fix (not proven)

- **Verdict:** `not_proven` — physical bg≥40s returned unlocked on `fda08e77-…`; fix republished
- **Evidence:** `ops/evidence/auth-wave2-phase3-autolock-timeout-fix-20260807T001808Z/`
- **Root causes addressed:** unstable AppState effect deps · async-before-seal · no background timer · weak diagnostics
- **OTA:** group `6cffdfd1-a7d9-4b1e-9d9e-5bb731fc2e5f` · env PIN=1 BIOMETRIC=1 AUTO_LOCK=1 · rollback `fda08e77-…`
- **Owner retest:** force-quit/reopen → confirm Auto-lock=30s → bg≥40s must Face ID/PIN; check logs `[autolock]` for updateId + SEALED
- **Phase 4:** not started · Phase 3 not marked proven

## 20260807T002604Z — Auth Wave 2 Phase 3 false-positive lock fix

- **Verdict:** `not_proven` — every leave/return locked on prior OTA; inactive + screen-probe false positives
- **Evidence:** `ops/evidence/auth-wave2-phase3-autolock-false-positive-fix-20260807T002520Z/`
- **Fix:** arm only on `background` · probe only while background · resume reasons `timeout|confirmed_device_lock|none` · cancel timers · no duplicate seal
- **OTA:** `0ac5d3b9-442e-422d-8bcc-39d0b1027346` · rollback `6cffdfd1-…`
- **Retest:** 5–15s away no prompt · ≥40s Face ID/PIN · phone lock Face ID/PIN · Control Center no false lock
- **Phase 4:** not started

## 20260807T003218Z — Auth Wave 2 Phase 3 FAILED (resume crash) + fix

- **Verdict:** `failed` on `0ac5d3b9-…` (leave → return hard crash after Face ID unlock)
- **Rollback:** republished `fda08e77-…` as live `83fe64f6-…`
- **Cause (code):** `setStatus('locked')` from background timer/probe + Face ID during AppState transition
- **Fix OTA:** `fdb4002c-d014-4cd1-aa12-0ff2f76aaa76` — resume-only seal · intent refs in background · delayed Face ID · single coordinator
- **Evidence:** `ops/evidence/auth-wave2-phase3-autolock-crash-fix-20260807T003131Z/`
- **Re-prove:** 10s no lock/crash · 40s one prompt · phone lock one prompt · Control Center clean · rapid ×10 no crash
- **Phase 4:** not started

## 20260807T054506Z — Phase 5: Re-invite one-time code modal fix

- **Finding:** After HR revoke, Re-invite hit a **pending** invite (`pending_activation_invite_exists`); canceling supersede exited silently — no new invite, no code modal
- **Fix:** Re-invite auto-supersedes pending · always success notice + one-time code modal · revoke supersedes pending invites
- **Evidence:** `ops/evidence/auth-wave2-phase5-reinvite-modal-fix-20260807T054506Z/`
- **Verdict:** Phase 5 still **fully proven** · **Phase 6 not started**

## 20260807T053517Z — Auth Wave 2 Phase 5: access-reset copy (close)

- **Finding:** HR revoke showed Session expired because `hr_revoked` → generic `app_auth_failed` → `session_expired`
- **Fix:** server `app_access_revoked` · client `access_reset` copy — **Your app access was reset** / Sign in again with a new activation code. Soft failures unchanged
- **OTA:** `7f1731ad-d482-4b7a-a2fc-502fa1a987c8`
- **Prove:** unit 38/38 · live revoke→`app_access_revoked`→refresh dead→re-invite activate
- **Evidence:** `ops/evidence/auth-wave2-phase5-access-reset-copy-20260807T053517Z/`
- **Verdict:** Phase 5 **fully proven** · **Phase 6 not started**

## 20260807T045603Z — Auth Wave 2 Phase 5: Basic device security

- **Scope:** Settings Device security · Sign out this device · new-device notice once · HR App access revoke/re-invite · one-device rule preserved
- **OTA:** `4cb17ad8-2fea-4f19-954d-95a418ec265d`
- **Backend:** `GET /app/device-security` · HR `.../app-access` + revoke · activate `replaced_previous_device` + platform
- **Prove:** Phase 5 unit 31/31 · public routes 401 (not 404) · dashboard dist shipped
- **Evidence:** `ops/evidence/auth-wave2-phase5-device-security-20260807T045603Z/`
- **Owner:** device details · sign-out · HR revoke kills session · old PIN/Face ID dead · new-phone notice once · offline/5xx no revoke
- **Verdict:** **partially proven** · **Phase 6 not started**

## 20260807T042705Z — Auth Wave 2 Phase 4: Forgot PIN confirm copy

- **Scope:** Confirm before reset — title **Reset your PIN?** · body activation-code + new PIN · **Cancel** / **Continue** · clear only after Continue
- **OTA:** `1f0fcfdb-0d27-4d21-97e6-d657bc7a589b`
- **Prove:** Phase 4 unit 29/29 · tsc PASS
- **Evidence:** `ops/evidence/auth-wave2-phase4-forgot-confirm-copy-20260807T042705Z/`
- **Verdict:** copy ship · recovery path unchanged · **Phase 5 not started**

## 20260807T041404Z — Auth Wave 2 Phase 4: Simple PIN recovery

- **Scope:** Forgot PIN? · confirm → clear PIN + biometric pref + session → activation · 5-fail same path · EN/AR
- **OTA:** `af0c0998-d41b-4f68-a2a2-3fabc06537c0`
- **Prove:** Phase 4 unit 24/24 · Phase 3 unit 61/61 · tsc PASS
- **Evidence:** `ops/evidence/auth-wave2-phase4-pin-recovery-20260807T041404Z/`
- **Owner:** Forgot PIN · old PIN/Face ID dead · activate + new PIN · wrong×5 same reset · no network false reset
- **Verdict:** **partially proven** · **Phase 5 not started**

## 20260807T035603Z — Auth Wave 2 Phase 3B nav preserve (under review)

- **Finding:** Face ID unlock may have restored a different screen; code path does **not** remount AuthGate / call router — likely RN Modal vs native-stack
- **Fix:** iOS unlock host → `FullWindowOverlay` · skip privacy cover + foreground refetch while overlay up · timeout/Face ID unchanged
- **OTA:** `9a9a11be-dc9a-4e01-a1ec-f6f98bc5e2de`
- **Prove:** unit 60/60
- **Evidence:** `ops/evidence/auth-wave2-phase3b-nav-preserve-20260807T035603Z/`
- **Owner:** leave on Settings/Bank → ≥40s → Face ID (and cancel→PIN) must return to **same screen**
- **Verdict:** Phase 3B **under review** · **Phase 4 not started**

## 20260807T030944Z — Auth Wave 2 Phase 3B Face ID arm fix

- **Finding:** `68f5d59c-…` overlay after 40s OK · no crash/OTP · **PIN only** (Face ID never prompted)
- **Cause:** `attempted=true` before authenticate + no AppState retry → single attempt consumed on resume settle
- **Fix:** rising-edge reset · commit only before prompt · AppState retry · Modal `overFullScreen` + onShow fallback · Settings bio gate reason · no preference wipe on transient !usable
- **OTA:** `9aa012bf-dec5-4c54-9bf0-db525484eeca`
- **Prove:** unit 56/56
- **Evidence:** `ops/evidence/auth-wave2-phase3b-faceid-arm-fix-20260807T030944Z/`
- **Verdict:** **partially proven** — retest Face ID prompt · **Phase 4 not started**

## 20260807T025428Z — Auth Wave 2 Phase 3B: Face ID on proven overlay

- **Scope:** Reuse cold-start `UnlockWithBiometricGate` inside Modal overlay · arm after `onShow` + stable active · success dismisses overlay only · cancel/fail → PIN same overlay
- **Unchanged:** timeout logic · no remount · no Wave 1 / SecureStore session / device-lock
- **OTA:** group `68f5d59c-c243-4f50-8361-6f49d7a7c5db` · AUTO_LOCK=1 · AUTO_LOCK_BIOMETRIC=1
- **Prove:** unit 48/48
- **Evidence:** `ops/evidence/auth-wave2-phase3b-overlay-faceid-20260807T025428Z/`
- **Owner:** &lt;30s none · ≥40s overlay→Face ID · success dismiss · cancel→PIN · wrong/correct PIN · CC clean · ×25 no crash · no OTP/logout/nav reset
- **Verdict:** **partially proven** — physical pending · **Phase 4 not started**

## 20260807T024253Z — Auth Wave 2 Phase 3 overlay Modal + Settings diagnostics

- **Finding:** `b9c90b4f` physical test — &lt;30s OK · ≥30s also no PIN overlay (activation failure / likely native-stack covering absolute View; console stripped)
- **Fix:** PIN overlay hosted in RN `Modal` · Settings canary panel (update ID, marker `al-overlay-v3:1`, enabled, timeout, last away/elapsed/decision) · Face ID still off
- **OTA:** group `f6364b3b-5b9f-4ec9-8c97-3ec22f560a89` · AUTO_LOCK=1 · AUTO_LOCK_BIOMETRIC=0
- **Prove:** unit 39/39
- **Evidence:** `ops/evidence/auth-wave2-phase3-overlay-diag-20260807T024253Z/`
- **Owner:** force-quit → confirm Settings diagnostics (marker `al-overlay-v3:1`, enabled yes, timeout 30000) → 5–15s none · ≥40s PIN Modal · CC clean · ×25 no crash. Stop if crash; no Face ID; no Phase 4
- **Verdict:** **not proven** — awaiting device

## 20260807T022920Z — Auth Wave 2 Phase 3 overlay rebuild (PIN-only)

- **Verdict:** prior Phase 3 `failed` (resume crashes). Rebuilt as `needsLocalUnlock` overlay; AuthGate stays mounted
- **Disable OTA:** `3c51b707-…` (AUTO_LOCK=0)
- **PIN-only prove OTA:** `b9c90b4f-83c7-42fe-8145-d2c991324417` (AUTO_LOCK=1, BIOMETRIC overlay=0) — **physical PIN overlay did not appear** (superseded by `f6364b3b-…`)
- **Evidence:** `ops/evidence/auth-wave2-phase3-overlay-rebuild-20260807T022817Z/`
- **Owner:** force-quit → 30s setting → 5–15s no overlay · 40s PIN overlay · CC clean · rapid ×25 no crash. Stop if crash; do not enable Face ID yet
- **Phase 4:** not started

## 20260807T194248Z — Employee↔HR Sync Hardening
- Dashboard: `PostHire-MwO0aeVW.js`
- OTA canary: `3d01d413-214f-4fa6-8ec5-3c10e48e8a1e`
- Evidence: `ops/evidence/employee-hr-sync-hardening-20260807T194248Z`
- Verdict: PASS (API + contracts; device foreground/unlock covered by wiring + OTA)

## 20260808T195345Z — Visual A–E deploy: backend Phase E + canary OTA

- **Backend:** commit `c80900c` → production `app.py` sha `144a608f…` (was `6dee3d6c…`), 128-line Phase E delta only. Backup `/opt/wathefni/backups/production-pre-employee-app-phaseE-20260808T195345Z` with `ROLLBACK.sh` (backup proven byte-identical to the running file; rollback cycle not exercised).
- **Backend prove:** `/app/leave/duration` 404 → **401** internally and via the public edge; 20-route before/after probe identical; health 200. Live-data run: Thu→Mon = 5 calendar / **3.0 chargeable** (fri/sat excluded, holidays excluded); reversed range abstains `invalid_range`; Home renewal detail projects EN/AR labels and correctly returns `None` when there are no renewals.
- **OTA:** group `c997eac8-8b33-4b55-9a8e-a1860d0420fe` · iOS `019fe2f8-0363-7f93-8095-2abeb8647013` · Android `019fe2f8-0363-7c06-a114-b216af08a9cb` · runtime `0.1.0` · branch/channel `canary` · source `1e77bf6` · **rollback group `f9fc3c25-f535-40e0-b273-ef3214da93c2`**.
- **No new native build:** installed iOS build `7b3dc831…` (0.1.0/11) `Expo.plist` confirms runtime `0.1.0`, channel canary, updates enabled. Binary inspected directly — every native module the current JS needs is compiled in, including `RCTLinking` for the Phase E Call action. `eas build:list`'s `cf26d595` commit label is not a usable dependency baseline (HEAD was a month stale against the working tree).
- **Known gap (pre-existing, not a regression):** `expo-screen-detector` is absent from the installed binary; `src/auth/deviceLock.ts` guards the require and falls back to timeout-based auto-lock. Fix in a future deliberate native build.
- **Carry into QA:** no canary employee currently has a document with a **dated** expiry, so the "expires in N days" Home copy is not observable on device without a seeded fixture.
- **Evidence:** `ops/evidence/employee-app-phaseE-backend-deploy-20260808T195345Z/` · `ops/evidence/employee-app-phaseE-canary-ota-20260808T200225Z/`
- **Verdict:** backend **PASS** · OTA **PASS** · device-on-latest **pending owner relaunch** (two launches required: `EXUpdatesLaunchWaitMs=0` downloads in background and applies on the next start)

## 20260808T204823Z — A1 RTL double-flip: root cause, fix, OTA

- **Finding (A, systemic):** Arabic was mirrored twice. Yoga's `resolveDirection()` turns `Row`→`RowReverse` under RTL and `RowReverse`→**`Row`**, so 42 manual `row-reverse` overrides laid Arabic rows out in Latin order. iOS `RCTTextAttributes.effectiveParagraphStyle` swaps `NSTextAlignmentLeft`/`Right` under RTL, so 54 `textAlign: isRTL ? 'right' : 'left'` sites pinned Arabic to the wrong edge. 96 sites, 14 files.
- **Proved from source, not eyeballed:** engine files ship in `node_modules`; Arabic reaches Yoga as RTL via both the root `direction: 'rtl'` prop and `forceRTL`, so the flip was unconditional.
- **Likely origin:** dev clients cannot `Updates.reloadAsync`, so native RTL never applied during development and manual flipping looked right. It only breaks in a production build that reloads.
- **Fix:** manual row flips removed (Yoga owns it); alignment routed through `readingEdgeAlign()`/`trailingEdgeAlign()`, which key off `I18nManager.isRTL` rather than locale so the degraded no-reload state stays correct. Native RTL **not** disabled. 11 direction-aware chevrons/arrows preserved — glyphs are content, not layout.
- **English unaffected by construction:** every removed branch was already false in LTR and `readingEdgeAlign(false)` returns the prior value.
- **Gates:** typecheck clean · 14 gates / 609 checks green · new `verify-rtl-single-source.py` (260 checks) proven to fail on a reintroduced flip and pass once reverted.
- **OTA:** group `9b4d8a79-a9d9-4fa5-9f5b-6471685a4219` · iOS `019fe322-4cc3-7507-adfd-04f5ba4cc758` · Android `019fe322-4cc3-75e3-95b0-7df9af333633` · runtime `0.1.0` · commit `3415887` · **rollback group `c997eac8-8b33-4b55-9a8e-a1860d0420fe`**
- **Evidence:** `ops/evidence/employee-app-physical-qa-phaseF-20260808T192633Z/RTL_ROOT_CAUSE_AND_FIX.md`
- **Verdict:** root cause **proven** · fix **shipped** · physical Arabic confirmation **pending owner**. All other physical QA verdicts (smoothness, transitions, scrolling, Dynamic Type, VoiceOver, offline, auth transitions) remain **BLOCKED** — no Xcode/simulator/device on the build machine.

## 20260808T211400Z — Technical physical QA (owner-executed)

- **Device:** physical iPhone on OTA `019fe322-4cc3-7507-adfd-04f5ba4cc758` · commit `3415887` · runtime `0.1.0` · channel canary
- **PASS:** `RTL_PHYSICAL` (A1 confirmed closed — Arabic starts right, chevrons left) · `RESPONSIVENESS` · `SMOOTHNESS` (tab switching, transitions and long-history scrolling all reported SMOOTH) · `TRANSITIONS` · `DYNAMIC_TYPE` (both AX5 suspects hold)
- **Not established:** `ACCESSIBILITY_PHYSICAL` — VoiceOver (T13) and Reduce Motion (T14) not run; cannot be inferred statically
- **Unreported:** T10 refresh-no-blank · T11 offline/reconnect · T12 submit states. **Untested:** T17 second device size (no Xcode/simulator on build machine)
- **Resolved open questions:** T1 proved the `KeyboardAvoidingView` + `automaticallyAdjustKeyboardInsets` pair composes rather than fights — left as-is. T3 proved the privacy cover wins the app-switcher snapshot race. T8 validated paging-inside-ScrollView over nested virtualization.
- **B1/B2 recorded, not changed:** fixed-height `countryCode` and 38×38 avatar are inconsistent with the flexible pattern around them but legible at AX5, so no churn.
- **C:** none — nothing aesthetic touched.
- **Regressions:** none · typecheck clean · 14 gates / 609 checks green
- **Evidence:** `ops/evidence/employee-app-physical-qa-phaseF-20260808T192633Z/TECHNICAL_QA_RESULT.md`
- **Closure:** owner elected to close with T10–T14 and T17 unrun. Recorded, not resolved — `ACCESSIBILITY_PHYSICAL` stays **not established** and is deliberately not folded into the pass. Run T13/T14 before any VoiceOver-dependent customer, ideally after the visual redesign moves focus order.
- **Verdict:** `TECHNICAL_PHYSICAL_QA` = **PASS over the scope tested** (RTL, responsiveness, smoothness, transitions, Dynamic Type) · `EMPLOYEE_APP_READY_FOR_OWNER_FREEZE` = **NO** (visual direction owner-rejected; dedicated redesign phase follows)

## 20260811T122043Z — Pre-Customer Architecture Hardening wave (production)

- **Scope:** one controlled wave closing every §5 must-fix from `ops/CANONICAL_MULTISURFACE_ARCHITECTURE_VERIFICATION.md` — onboarding tenant column + scoped reads/writes, candidate tenant integrity (backfill 8, audited delete of 7 unreferenced fixtures, `NOT NULL`), real leave provenance per surface, HR Web task `expected_status` stale-write guard, honest queue pagination + urgent ordering, HR Mobile foreground/focus/unlock convergence, `no-store` on authenticated surface reads.
- **Backend:** `app.py`, `operator_mobile_data.py`, `outbound_delivery.py`, `action_registry.py`, `onboarding_wave2.py`, `employee_migration_lifecycle.py` · schema applied under the deploy advisory lock (`onboarding_items` 258/258 stamped, `candidates.active_company_code` NOT NULL, 0 NULLs).
- **HR Web:** bundle rebuilt and shipped to `/opt/wathefni/dashboard-dist` (the served root per the Caddyfile) — resolve now sends `expected_status` and handles 409 `stale_decision`. Prior bundle: `/opt/wathefni/backups/dashboard-dist-20260811T124800Z`. Note for future waves: `/var/www/wathefni-dashboard` in older deploy scripts is no longer served.
- **OTA:** branch/channel `canary` · runtime `0.3.0` · group `927e90c7-16db-4cd8-8957-29622942f35a` · iOS `019ff0da-121b-7e15-9868-e5ef11030085` · Android `019ff0da-121b-7f3b-a0a7-005074b4643c` · **rollback group `75042c41-ca1b-4e10-8306-dd16c84c256c`**. JS only — no native change, no new native dependency.
- **Proofs:** canonical multi-surface harness P1–P6 **PASS** · new hardening harness H1–H7 **PASS** (13/13). Synthetic fixtures only; both harnesses self-clean (0 rows left behind).
- **Regressions:** dashboard 465/465 tests green · mobile typecheck clean (also fixed a pre-existing `typography.small` token in the HR confirm sheet) · Python compile clean.
- **Accepted debt:** reconnect detection is indirect (no `NetInfo` without a native build; foreground + screen focus cover it) · Inbox shows an honest count rather than Load more because the priorities endpoint is a 30-item window by design · attendance exceptions are filtered twice (totals stay honest) · hiring/pre-hire queues out of scope.
- **Evidence:** `ops/evidence/pre-customer-hardening-20260811T122043Z/` (both harness JSONs, harness sources, deploy script, `ROLLBACK.sh`) · report `ops/PRE_CUSTOMER_ARCHITECTURE_HARDENING.md`.
- **Verdict:** **PRE-CUSTOMER ARCHITECTURE HARDENING PASS** — no remaining blocker before onboarding the first real company.
