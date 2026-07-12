# Phase 7E — Employee app readiness checklist (plan only)

**Status:** E2 evidence accepted — **not staging-green**. Phase 7E remains open. Phase 8 must not begin. No production enablement authorized. Next gate: **Phase 7E-R1 remediation plan** (`ops/PHASE7E_R1_REMEDIATION_PLAN.md`) — plan only until approved; no application patches yet.  
**E1 artifacts:** `ops/PHASE7E_E1A_PILOT_SHEET.md`, `ops/PHASE7E_E1B_PRIVACY_CHECKLIST.md`.  
**E2 artifacts:** `ops/staging-phase7e-employee-app-verify.py`, `ops/reports/phase7e-e2-verifier-report.json`, `ops/reports/phase7e-e2-verifier-report.md`.  
**R1 plan:** `ops/PHASE7E_R1_REMEDIATION_PLAN.md` (R1A identity/lifecycle/session; R1B upload content validation). C07k/C07l deferred out of R1.

**Prerequisites closed:** Phase 7A–7D (Setup Console / workspace boot, onboarding-seed staging pack, compliance docs reconcile series, company channel accounts **staging-ready / production-dark**).

**Keep OFF everywhere (including any future staging flag window until separately approved for E2):**

- `WATHEFNI_EMPLOYEE_APP=off`
- `WATHEFNI_ONBOARDING_SEED=off`
- `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`

Do **not** promote Phase 7D routing. Do **not** mix unrelated production changes into 7E.

**Hard non-goals for Phase 7E:**

- Do **not** enable `WATHEFNI_EMPLOYEE_APP` (staging window for E2 only after E1 complete + explicit staging-window approval)  
- Do **not** enable `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS`  
- Do **not** enable `WATHEFNI_ONBOARDING_SEED`  
- Do **not** create or activate a **production** pilot company during Phase 7E  
- Do **not** treat Phase 7E completion as authorization for production enablement — that is a **separate Phase 8 decision and gate**  
- Do **not** treat UI visibility / nav hiding as authorization or rollback  

---

## Goal

Make employee-app continuation safe by defining:

1. What backend authorization must enforce on every `/app/*` request  
2. What invite, upload, delivery, and kill-switch proofs must pass on staging  
3. What operational artifacts (pilot sheet, privacy checklist) must exist before E2 coding and before any later Phase 8 production decision  

Phase 7E answers readiness. It does **not** turn the app on in production.

---

## Approved execution order (Decision 2)

| Step | Work | Output | Flags |
|------|------|--------|-------|
| **E1a** | Complete pilot sheet (§4) | Filled planning artifact only — no prod company create/activate | all protected OFF |
| **E1b** | Complete privacy readiness checklist (§9) | Documented answers + blockers list | all protected OFF |
| **E2** | Staging verifier on `P7ESTG01` (+ companion throwaways as needed) | Green matrix + rollback drill record | staging flag window only if approved; prod unchanged |
| **Exit** | §12 exit criteria | 7E closed as staging-ready / production-dark | all production flags unchanged |
| **Not in 7E** | Production pilot activation | Separate Phase 8 RFC | — |

---

## 1. What is already ready (unchanged spine)

| Area | State |
|------|--------|
| Master dark-launch gate | `employee_app_enabled()`; `/app/*` inert when OFF |
| Per-company module | `company_modules.employee_app`; Setup Console configured vs effective |
| Backend `/app/*` + HR invite | Built behind gates |
| Session model | Server-side employee resolution; IDOR-resistant design intent |
| Offboarding revoke helper | `revoke_employee_app_access()` |
| Mobile scaffold + draft docs | `apps/wathefni-employee-mobile` + PRIVACY/ROLLOUT/STORE_REVIEW |
| Shared WhatsApp routing | Production path; 7D stays dark |
| Document storage reuse | Same Document Hub pipeline; independent of channel accounts |

**Interpretation:** spine exists; 7E proves **authorization, invite safety, upload security, delivery honesty, and immediate revocation** — not greenfield product build.

---

## 2. What is still missing (before Phase 8)

| Gap | Owner stream |
|-----|----------------|
| Completed pilot sheet (§4) — planning only | E1a |
| Expanded privacy checklist (§9) | E1b |
| Every-request gate proof (§3) | E2 |
| Invite negative matrix (§5) | E2 |
| Option A checklist honesty + unseeded non-crash (§6) | E1 + E2 |
| Upload security + orphan/audit proofs (§7) | E2 |
| Outbound delivery state machine honesty (§8) | E1 policy + E2 |
| Kill-switch proofs beyond nav hiding (§10) | E2 |
| Staging matrix green + rollback record (§11–§12) | E2 |

---

## 3. Backend authorization — every `/app/*` request

**UI visibility is not an authorization control.** Hiding a tab, disabling a button, or omitting a nav item must never be the only gate.

### Required conjunctive gates (all applicable must pass)

On **every** authenticated `/app/*` request (and on activate/refresh where applicable):

| Gate | Rule |
|------|------|
| Global employee-app flag | `WATHEFNI_EMPLOYEE_APP` ON; else fail closed (e.g. 503) |
| Active company lifecycle | Company must be active — not disabled / archived / otherwise ineligible |
| Effective company `employee_app` module | Module configured **and** platform-available **and** enabled for that company |
| Active / eligible employee | Employee must be active/eligible for app access (e.g. not `left` / revoked) |
| Valid non-revoked session | Bearer/session must be present, valid, unbound to revoked sessions/tokens |

Unauthenticated endpoints in the surface (e.g. activate with phone+code) still require: global flag ON, company active, module effective, employee eligible, and invite validity (§5).

### E2 proof requirement

For each gate, prove that flipping **only that gate** blocks subsequent API access even when the client still holds a previously issued token (where session-based) or retries activate (where invite-based). Success is measured by **API status codes / error bodies**, not by whether the mobile UI still shows a screen.

---

## 4. Pilot sheet (E1a — required before E2)

**Purpose:** plan a future Phase 8 production pilot.  
**Forbidden during 7E:** creating, enabling modules for, inviting, or activating a **production** pilot company.

### Required fields (all must be filled)

| Field | Requirement |
|-------|-------------|
| One pilot company | Single company code (named intent only in 7E) |
| Qualification reason | Why this company is first (consent, readiness, supportability) |
| Small cohort size | Numeric cap (e.g. 3–10); no open enrollment |
| HR owner | Named person responsible for invites + employee support |
| Rollback owner | Named person authorized to flip flags / disable module |
| Included workflows | Explicit list (e.g. activate, inbox, onboarding upload, leave, …) |
| Excluded workflows | Explicit list (e.g. push, payroll surfaces, company WhatsApp, seed, …) |
| Success criteria | Measurable (activation rate, upload success, no cross-tenant incidents, …) |
| Stop criteria | Abort triggers (delivery silent-fail, tenant leak, support overload, need for 7D prod, …) |

### Template

```text
Pilot company (intent only): ________
Qualification reason: ________
Cohort size (max): ________
HR owner: ________
Rollback owner: ________
Included workflows: ________
Excluded workflows: ________
Success criteria: ________
Stop criteria: ________
Outbound mode (§8): inbox-only | shared-WhatsApp/email fallback via existing policy
Onboarding mode (§6): Option A with explicit manual checklist provisioning
7E note: no production company create/activate in this phase
```

Staging throwaways (`P7ESTG01`, …) are **not** the production pilot company. They exist only for E2 proofs.

---

## 5. Invite validation matrix (E2 must cover)

Happy path remains: HR invite → one-time code → activate → session.

**Explicit negative / edge cases (all required):**

| Case | Expect |
|------|--------|
| Expired invite | Activate rejected; no session |
| Reused invite (already redeemed) | Second activate rejected |
| Revoked / superseded invite | Old code rejected after re-issue or revoke |
| Wrong employee (code for A, phone of B) | Rejected; no cross-employee bind |
| Wrong company | Rejected; no cross-tenant bind |
| Disabled company | Invite and/or activate rejected |
| Archived company | Invite and/or activate rejected |
| Already-activated employee | Re-activate with same/old code rejected or safely no-ops without issuing a privileged second identity; policy must be explicit and tested |

Also prove: delivery failure surfaces as an operator-visible outcome (`hr_task` / failed delivery state) — never silent success.

---

## 6. Onboarding seed — Option A with hard honesty rules

`WATHEFNI_ONBOARDING_SEED` remains **off**.

**Option A is accepted only if** the pilot checklist is **manually and explicitly provisioned** for each pilot employee (HR/dashboard/hire path — not implied, not invented by the app).

### Required proofs (E2)

| Case | Expect |
|------|--------|
| Unseeded company / employee with zero checklist rows | API does **not** crash |
| Empty checklist representation | Does **not** invent checklist items |
| “No checklist assigned” | Must **not** be interpreted as completed / ready |
| Option A employee with explicitly provisioned items | Checklist returns those items only; upload allowed only for owned `item_id`s |

Staging may insert explicit fixture checklist rows for throwaway employees. That is **not** enabling production seed.

---

## 7. Document upload security (E2 must cover)

Upload remains `POST /app/onboarding/documents` on the shared Document Hub pipeline. Independent of 7D channel accounts.

### Required proofs

| Concern | Expect |
|---------|--------|
| Tenant ownership | Upload bound to session company; cannot attach to another company |
| Employee ownership | `item_id` must already belong to the authenticated employee |
| Cross-tenant denial | Employee A (co1) cannot upload/read co2 docs |
| Cross-employee denial | Employee A cannot upload/read employee B items/files in same company |
| MIME / extension enforcement | Disallowed types rejected |
| Size enforcement | Over-cap rejected |
| Canonical Document Hub metadata | Successful upload produces consistent registry / receipt / onboarding item linkage HR can trust |
| Failed-write orphan safety | Failed storage/DB path does not leave untracked orphan files as “success”; no false completed state |
| Auditability | Upload (and denial where applicable) is auditable |
| Access after employee revoke | Prior bearer cannot upload or download; revoke is immediate for API access |

---

## 8. Outbound delivery policy for the pilot

### Allowed modes

- **Inbox-only** — allowed for pilot if sheet says so (`WATHEFNI_PUSH_NOTIFICATIONS` may stay off).  
- **Shared WhatsApp / email fallback** — allowed **only** through existing outbound policy / ladder (7D company-owned routing stays OFF).

### Backend honesty requirement

The backend must distinguish at least these outcomes (names may map to existing `outbound_delivery` / message statuses, but semantics must be clear and testable):

| Outcome | Meaning |
|---------|---------|
| `created` | Logical message / invite record exists |
| `attempted` | A channel send was tried |
| `delivered` | Provider/channel acknowledged success (or equivalent durable success signal) |
| `failed` | Attempt exhausted without success |
| `suppressed` | Intentionally not sent (opt-out / policy) |
| `fallback` | Primary channel skipped/failed; secondary channel used per policy |

**UI must not invent delivery state.** Clients may only display server-provided statuses. Missing/unknown ≠ delivered.

### E2 proofs

- Invite/notification path records honest states under dry-run / mocked provider as applicable  
- Inbox-only mode does not fabricate WhatsApp/push “delivered”  
- Fallback, when used, is labeled as fallback — not as primary success without evidence  

---

## 9. Privacy readiness (E1b — expanded)

Drafts in `apps/wathefni-employee-mobile/docs/` are starting points. E1b must complete a checklist covering **more than URL/assets**:

| Topic | Must document |
|-------|----------------|
| Privacy policy URL | Stable public URL + in-app Settings + store listings (blocker for external tracks) |
| App icon / splash | No Expo placeholders before external tracks |
| Build API base URL | Correct per EAS profile |
| Data collected | Phone/name, employment data surfaces, uploads, push token, device/app info — exact list |
| Document categories | Which doc types employees may upload; what HR sees |
| Retention / deletion | How long docs/sessions/tokens retained; who deletes; employer-as-controller model |
| Employee account closure | In-app deletion **request** → HR task; what happens to sessions/tokens; what does **not** auto-wipe |
| Support contact | Who employees/HR contact for privacy/access issues |
| Permissions | Notifications (optional), camera/photos (upload only); no location/contacts/ads ID |
| Analytics / crash tools | Which SDKs (if any); what is disabled; crash reporting posture |
| External provider sharing | Expo push, WhatsApp/email providers, storage providers — what leaves Wathefni and why |

E1b output is a completed checklist document/section (may live as `ops/PHASE7E_PRIVACY_CHECKLIST.md` when implementation of E1 artifacts is authorized). **This plan revision does not create that file yet** beyond defining the requirement.

---

## 10. Kill switch / rollback (API-level proof)

Navigation hiding is **not** rollback.

### Levers that must each block subsequent authenticated API access

| Lever | Expect after action |
|-------|---------------------|
| Global flag OFF | Existing session → `/app/*` denied (e.g. 503); new activate denied |
| Company `employee_app` module removed / disabled | Existing session → denied; invite/activate denied for that company |
| Company disable / archive | Existing session → denied; invite/activate denied |
| Per-employee revoke | That employee’s session/tokens → denied immediately; other employees unaffected |

Also confirm: HR dashboard and shared WhatsApp/email paths remain available (no collateral dark-launch of unrelated surfaces).

### Rollback drill record (required for exit)

Record timestamp, actor, lever used, API evidence (status codes), and confirmation that production flags remained unchanged after the staging window.

---

## 11. Staging validation (E2) — `P7ESTG01`

**Throwaway only.** Production `WATHEFNI_*` protected flags stay OFF.  
Do **not** force an exact case count. Start from the **12 core cases** below; **add cases as needed** until tenant isolation, invite safety, upload security, and immediate revocation are proven.

### Core cases (minimum)

| # | Case | Expect |
|---|------|--------|
| 1 | Flag OFF baseline | `/app/*` denied; invite denied; module not effective |
| 2 | Flag ON + module OFF | Invite/activate/session denied |
| 3 | Flag ON + module ON + invite happy path | Code issued; delivery outcome honest (`created`/`attempted`/…) |
| 4 | Activate happy path | Session issued; `/app/me` self-scoped |
| 5 | Tenant isolation | CoB cannot read/act as CoA |
| 6 | Onboarding Option A + unseeded honesty | Explicit items work; empty ≠ completed; no invent/crash |
| 7 | Upload security suite | Ownership, MIME/size, hub metadata, orphan safety, audit |
| 8 | Leave (if included) | Happy path + module-off clear error |
| 9 | Inbox without inventing delivery | Read/mark works; no fabricated channel delivery |
| 10 | Immediate revocation suite | Flag / module / company lifecycle / employee revoke each deny API |
| 11 | Protected flags | After window: prod+staging employee app OFF unless staging window still open and documented; channel accounts OFF; seed OFF |
| 12 | Invite negative suite | Expired, reused, revoked/superseded, wrong-employee, wrong-company, disabled/archived company, already-activated |

### Additive cases (add freely when needed)

Examples: refresh-after-revoke, document GET after revoke, cross-employee file_id guess, suppressed delivery, fallback labeling, disabled vs archived company distinction, concurrent re-invite supersede.

### Proposed artifact (when E2 coding is authorized)

`ops/staging-phase7e-employee-app-verify.py` against staging DB + staging orchestrator. Mocked/dry-run sends only unless a separately approved live-channel rehearsal is written (default: no live WhatsApp requirement for matrix green).

---

## 12. Phase 7E exit criteria

Phase 7E is complete **only when all** are true:

| # | Criterion |
|---|-----------|
| 1 | Pilot sheet complete (§4) — planning artifact only |
| 2 | Privacy checklist complete (§9) |
| 3 | E2 staging verifier green on `P7ESTG01` (and any required companion throwaways) |
| 4 | Rollback / kill-switch drill recorded (§10) with API evidence |
| 5 | All production protected flags unchanged (`EMPLOYEE_APP`, `COMPANY_CHANNEL_ACCOUNTS`, `ONBOARDING_SEED` remain OFF) |

**Phase 7E completion does not authorize production enablement.**  
Any production employee-app pilot activation requires a **separate Phase 8 decision and gate**.

---

## Relationship to other phases

| Phase | Relationship |
|-------|----------------|
| 7B seed | Stays OFF; Option A uses manual checklist only |
| 7C reconcile | Not a 7E gate |
| 7D channel accounts | Staging-ready / production-dark; not promoted |
| 8 | App continuation + any production pilot enablement RFC |

---

## Workstreams (Decision 2)

| Stream | When | Output |
|--------|------|--------|
| E0 | Now | This revised plan accepted |
| **E1a** | Next | Completed pilot sheet (§4) — no prod activate |
| **E1b** | Next (parallel OK) | Completed privacy checklist (§9) |
| **E2** | After E1a+E1b | Staging verifier green + rollback record |
| E3 | After exit | Phase 8 production-pilot RFC only if desired — separate approval |

---

## Authorization statement

**This document does not authorize enabling `WATHEFNI_EMPLOYEE_APP`, `WATHEFNI_ONBOARDING_SEED`, or `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS` in staging or production.**  
**This document does not authorize creating or activating a production pilot company.**  
**UI visibility is never sufficient authorization or rollback.**
