# Wathefni Multi-User Company Workspaces — Read-Only Audit

**Date:** 2026-07-28 (Asia/Kuwait)  
**Scope:** How multiple employees of the same company log in and share data  
**Method:** Deployed-source inspection of `wathefni-orchestrator` + `apps/wathefni-dashboard`  
**Contributing deep dives:** [Audit RBAC and tenant isolation](f2643ce0-ed78-4d0b-9159-3efad8c802ef), [Audit shared data and scopes](887c7ce2-c482-4023-9896-9e9fb3b01c32)  
**Follow-up shipped:** `ops/MULTI_USER_WAVE1_ROLE_TAXONOMY.md` (role taxonomy cutover; Calendar still NO-GO)  
**Production mutations:** none (audit); Wave 1 deployed separately under stamp `20260728T210539Z`  

---

## Final verdict

**PASS for multi-user company workspaces at the tenancy + role layer.**  
**PARTIAL for fine-grained team/owner scoping and calendar readiness.**

Multiple users from one company already authenticate as separate `dashboard_users`, hold separate sessions, and share company hiring/post-hire data under role permissions. Tenant isolation by `company_code` is the primary hard boundary.

The architecture is **safe enough for many concurrent company users** for day-to-day HR work, with important caveats:

1. most pre-hiring data is **company-wide among permitted roles**, not private per recruiter by default;
2. there is **no first-class Wathefni Calendar** product yet—only Google Calendar attachments on interviews;
3. concurrent editing protection exists for jobs + candidate ownership/lifecycle paths, **not** as a general page-level lock;
4. product labels like “Company Admin / HR Admin / Payroll / Employee” do **not** map 1:1 to distinct dashboard roles today.

---

## How multiple employees from the same company log in

### Membership model

| Concept | Implementation |
|---|---|
| User row | `dashboard_users` (`user_id`, `company_code`, `email`, `name`, `phone`, `role`, `status`, password hash, invite metadata) |
| Uniqueness | `UNIQUE (company_code, email)` — same email may exist in **another company** as a different user row |
| Session | `dashboard_user_sessions` (`user_id`, `company_code`, `token_hash`, `status`, `expires_at`) |
| Extra grants | `dashboard_user_permission_grants` (grant-only scopes such as `employees.*`, `offer.hire_override`, `assessment.publish`) |

**Normal login:** `POST /dashboard/auth/login` with email + password + `company_code` → hashed session token (~14-day expiry) stored client-side and sent as bearer/`X-Dashboard-Token` plus `X-Company-Code`.

**Invite path:** Only `owner` has `users.manage` by default → `POST /dashboard/team/invites` → invitee accepts via `POST /dashboard/team/invites/accept` (sets password, activates user, creates session). Owner bootstrap for a new company is seeded from Setup Console / Super Admin.

**Session authority:** `dashboard_context()` resolves the session user, binds `company_code` from that user (not from a client-chosen tenant), rejects mismatched `X-Company-Code`, and requires `status=active` + active company lifecycle. `permission_authority` is `backend_current`.

**Legacy path:** Shared dashboard token + `X-HR-Phone` / `X-Company-Code` still exists in code as `legacy_untrusted`, but is disabled on normal production/staging unless an explicit harness flag is on. Recovery bootstrap users (`.wathefni.local`) are treated as temporary, not everyday multi-user identity.

### Sharing model in one sentence

Each user has a **personal login session**, but almost all hiring records live in **company-scoped tables**. Anyone with the right permission sees the same live database rows after refresh—there is no separate per-user copy of candidates, jobs, interviews, or assessments.

---

## 1. Company / tenant isolation

**Authority:** every dashboard context returns `company_code` from the authenticated user/session; list/query paths filter `WHERE company_code=%s`.

**Hard gates:**

- session company cannot be overridden by a different client header (`dashboard_company_forbidden`);
- company lifecycle (`require_active_company`) blocks disabled/archived tenants;
- Super Admin / Setup Console company-control paths are separate from normal HR dashboard sessions and audit against the **target** company.

**Assessment:** tenant isolation is systemic and production-grade for authenticated dashboard routes. Soft spots (not default HR paths):

- session lookup is by token hash and does not re-assert `session.company_code = user.company_code` (company still comes from the user row);
- some WhatsApp phone helpers can resolve a phone without a company argument;
- legacy helpers sometimes default `company_code` to `WATHEFNI` when callers omit it;
- `GET /dashboard/team` is company-scoped but **does not require `users.manage`** — any active member can list peer emails/roles/effective permissions (mutations still require `users.manage`).

---

## 2. User membership

| Status | Meaning |
|---|---|
| `invited` | Invited; cannot use normal active session until acceptance |
| `active` | Normal workspace operator |
| `disabled` | Blocked; sessions + WhatsApp identities revoked on disable paths |

**Multi-company:** a person can belong to multiple companies only as **separate user rows** (separate emails-per-company uniqueness). One session is always one company. There is **no company switcher** in the dashboard UI (one `wathefni_company_code` in localStorage).

**Team surface:** Settings → Team lists company users/invites. Role change / disable requires `users.manage` (Owner only by default). WhatsApp-linked badge is company-scoped and does not expose phone numbers in that badge path. Disable is blocked when the user still owns active applications.

---

## 3. Roles and permissions (current fixed authority)

Canonical fixed roles live in `ROLE_PERMISSIONS` / `ROLE_LABELS` in `wathefni-orchestrator/app.py`.  
A Wave-2 `tenant_control_roles.py` layer exists for future custom roles/grants, but **does not replace** fixed HR roles authoritatively today.

### Actual dashboard roles

| Role key | UI label | Intended audience |
|---|---|---|
| `owner` | Owner / Admin (backend also “Owner / Super Admin”) | Company-wide control |
| `hr_manager` | HR Manager | Full HR ops + settings, not user invites unless granted |
| `manager` | Team Manager | Post-hire team lead with **manager_scopes** |
| `recruiter` | Recruiter / HR Officer | Hiring ops |
| `hiring_manager` | Hiring Manager | Read/review + interview + limited post-hire |
| `viewer` | Viewer | Read-mostly |

Aliases of note:

- `company_admin` → **`owner`**
- `hr_admin` → **`owner`**
- `admin` / `super_admin` → **`owner`**

There is **no separate dashboard role** named Payroll or Employee.

### Product-role mapping (requested labels)

**Target product taxonomy (authoritative intent as of 2026-07-28):**

| Target role | Proposed key | Current state | Gap |
|---|---|---|---|
| Company Admin | `company_admin` (today collapses → `owner`) | Alias of `owner` | Needs distinct key; keep `users.manage` + full company control |
| HR Admin | `hr_admin` (today collapses → `owner`) | Alias of `owner` | Must **stop** aliasing to Owner; between Company Admin and HR Manager |
| HR Manager | `hr_manager` | Exists | Align label; already closest match |
| Recruiter | `recruiter` | Exists | Align label (drop “HR Officer” if product wants clean name) |
| Hiring Manager | `hiring_manager` | Exists | Align label |
| Interviewer | `interviewer` | **Missing** | Panel assignment only today; needs dashboard role + interview-scoped ACL |
| Payroll Operator | `payroll_operator` | **Missing** | Payroll is permission bundle on Owner/HR Manager today |
| Viewer | `viewer` | Exists | Keep |
| Employee App user | (not a dashboard role) | Separate `/app/*` | Keep separate |

**Not in target list but live today:** `manager` (Team Manager) — post-hire scoped lead. Decide keep / rename / retire before taxonomy cutover.

| Product label | Current Wathefni mapping | Notes |
|---|---|---|
| Company Admin | `owner` | Aliases include `admin`, `company_admin`, `super_admin`, **`hr_admin`** → all collapse to `owner` |
| HR Admin | Product intent ≠ code: `hr_admin` → **`owner`** | Naming trap: inviting “HR Admin” grants full Owner powers |
| HR Manager | `hr_manager` | Exists; settings yes, `users.manage` no |
| Recruiter | `recruiter` | Can create/edit jobs (not publish/close by default), manage candidates/interviews/assessments/offers (send, not always approve) |
| Hiring Manager | `hiring_manager` | `prehire.read`, jobs read, interview manage, offer approve, notes/tasks collaborate; **no** `candidate.manage` / import / assessment manage |
| Interviewer | **No dashboard role** | Panel assignment is metadata; access is still company + `interview.manage` |
| Payroll Operator | **No dashboard role** | `payroll.read` / `payroll.manage` / `payroll.export` are permissions on other roles |
| Viewer | `viewer` | Read-mostly |
| Employee | Separate **Employee App** (`/app/*`, `employee_app_context`) | Not a dashboard role; self-scoped employee session |
| Team Manager (legacy live) | `manager` | Not in target taxonomy above — still live with `manager_scopes` |

### Permission resolution

1. Start from role defaults in `ROLE_PERMISSIONS`.
2. Strip grant-only families (`employees.*`, `offer.hire_override`, `assessment.publish`).
3. Add active rows from `dashboard_user_permission_grants`.
4. Module entitlement (`company_has_module`) still gates surfaces on top of permissions.
5. Frontend mirrors with `hasDashboardPermission` / Jobs compatibility for `settings.manage`.

---

## 4. Team and manager scope

**Org hierarchy V1** uses:

- `manager_scopes` (company + manager phone / `dashboard_user_id`)
- `manager_scope_members` (explicit employee list)

**Behavior:**

- Team Managers are fail-closed if scope is missing/conflicted/empty.
- Owners/HR without a manager_scopes row are **not** restricted by that mechanism; their authority is permission-based and company-wide for entitled modules.
- HR tasks / some post-hire queues are manager-scope aware: scoped managers see their people; company-wide tasks remain with HR.

**Pre-hiring does not generally use manager_scopes** to hide candidates from recruiters/hiring managers. Pre-hire visibility is permission + optional owner filters.

---

## 5. Job ownership

Jobs/positions are **company records** (`positions` keyed by company + position code).

- Attribution fields: `created_by_user_id`, `updated_by_user_id`, `recruiter_user_id`, `hiring_manager_user_id`, plus a job `version`.
- Filtering by recruiter/HM is supported as **optional query filters**, but **default job inventory is company-wide** for users with Jobs/`prehire` read.
- Create/edit/publish/close are permission-gated (`jobs.*`), **not** “only the assigned recruiter.”
- Jobs do use optimistic concurrency (`expected` version / `stale_job_version` / `stale_job_update` → 409).

**Classification:** company-wide shared, with soft ownership metadata — **not** personal private jobs. Assigned recruiter/HM does **not** form a hard edit ACL.

---

## 6. Candidate access

Applications/candidates are **company-scoped**.

- Default API scope is `owner_scope=all` (entire company cohort visible to permitted roles).
- Optional scopes: `mine` / `unassigned` / `assigned`, plus `recruiter_owner` filter when unified candidates is enabled.
- Stock dashboard UI does **not** force `owner_scope=mine`; ownership filters are optional.
- Ownership fields: `applications.owner_user_id`, governance `recruiter_owner_user_id`.
- Ownership/lifecycle mutations use version checks (`stale_ownership_version`, `stale_lifecycle_version` → HTTP 409).
- Manager scopes **do not** hide pre-hire candidates.

**Important product truth:** a Recruiter or Hiring Manager with `prehire.read` / `candidates.read` can see the company’s candidate pipeline unless explicitly filtered. There is **no automatic private inbox** per recruiter.

**Classification:**

- Shared company-wide among permitted prehire readers.
- Permission-scoped for mutations (`candidate.manage`, decide, import, C2/C3 privacy/merge grants).
- Ownership is collaborative metadata, not a hard visibility wall by default.

---

## 7. Interview and assessment access

| Surface | Visibility | Mutation gate |
|---|---|---|
| Interviews list/drawer / agenda | Company-wide for entitled prehire/interview readers | `interview.manage` + presentation `allowed_actions` |
| Interviewer / panel assignment | Stored on interview (`candidate_interview_assignments`); optional soft list filter | Assign interviewer operational action — **not** a hard “assignee-only” ACL |
| Assessments send/attempts/reports | Company-wide operational queues for `assessment.manage` | `assessment.manage`; publishing is grant-only (`assessment.publish`) |
| Assessment authoring/admin | Separated for normal HR (Wave 4 role separation) | Admin/elevated permissions |

Async/live interview state is backend-authoritative (`interview_presentation_v1`); assessments use `assessment_presentation_v1` / report presentation. These contracts are company-tenant scoped, not personal.

**Classification:** company-shared operational data; actions permission-scoped; interviewer assignment is soft metadata.

---

## 8. Calendar visibility / shared vs personal events

**Current state:**

- Interviews may sync **Google Calendar** events (`calendar_event_id`, `calendar_invite_sent`, Meet links) via the platform Google operator account (`GOG_ACCOUNT` → Google `primary`).
- Candidate + panel emails are invitees on that **shared** operator calendar, not each Wathefni user’s personal Google calendar.
- Agenda UI is the company interview agenda from Postgres, not per-user free/busy.
- There is **no** first-class Wathefni calendar of personal vs team events, free/busy, or per-user calendar ACLs in the dashboard.

**Classification today:**

| Data | Type |
|---|---|
| Interview schedule fields + Meet/calendar IDs on `candidate_interviews` | Company hiring record (shared) |
| External Google Calendar event | **Platform-shared operator mailbox/calendar** (not per-user Wathefni RBAC) |
| Wathefni personal calendar | **Does not exist yet** |

---

## 9. Action audit history

- Company Activity: `GET /dashboard/activity` requires `audit.read` (Owner + HR Manager by role defaults).
- Rows are company-scoped; filterable by actor user/email/phone.
- Mutations commonly call `record_admin_audit` / `write_admin_audit` with actor identity from context.
- Routine notification policy explicitly keeps many routine events in activity/audit rather than interruptive alerts.

**Classification:** company-shared audit trail; permission-scoped to readers with `audit.read`.

---

## 10. Concurrent editing protection

| Area | Protection |
|---|---|
| Jobs | Optimistic `version` / expected timestamp → `409 stale_job_version` / `stale_job_update` |
| Candidate ownership / lifecycle | Optimistic version → `409 stale_ownership_version` / `stale_lifecycle_version` |
| Assessment attempts / authoring transitions | Many `409` conflict envelopes |
| Video interview retakes / completion | State conflict `409`s |
| Company settings JSON | Last-write-wins merge (no version) |
| Notes/tasks general fields | Mixed; ownership/lifecycle covered more than free-text races |
| Dashboard UI | No live collaborative locks / presence |

**Assessment:** solid on jobs + selected lifecycle authorities; **weak as a general multi-editor UX**. Two recruiters can still race on non-versioned fields and shared settings.

---

## 11. Notifications and assigned tasks

### Pre-hire notifications (`/dashboard/prehire/notifications`)

- Company-scoped outbound delivery failures / action items.
- Policy: interrupt only for urgent/important classes; routine work stays in module queues.
- **Not a personal inbox** — any entitled user sees the same company delivery pressure.

### HR tasks (`/dashboard/hr-tasks`)

- Company-scoped task queue with optional manager-scope filtering.
- `assigned_to_user_id` exists on `hr_tasks`.
- Resolve requires manage-capable permissions.

### Candidate tasks / notes (C2)

- Collaborative candidate work items; ownership/assignment fields exist.
- Visible within company candidate collaboration permissions.

---

## 12. Do changes appear immediately to other users?

**Yes for data truth; no for push UI.**

- All entitled users read the same Postgres company rows.
- There is no dashboard-wide websocket/presence layer observed for Overview/Candidates/Jobs.
- Another user’s change appears on the next fetch/refresh/navigation (and any polling a page already does).
- Assistant chat sessions are indexed by `company_code` + `actor_user_id` — **personal conversation history**, not a shared company transcript.

---

## 13. Single-user assumptions (gaps / leftovers)

| Assumption | Status |
|---|---|
| One shared dashboard token for the company | Legacy; disabled on normal prod paths |
| One HR phone as identity | Legacy compatibility / recovery; normal path is per-user email session |
| One operator per company | **False** — multi-user team invites are first-class |
| Chat storage keyed partly by phone in localStorage | Frontend helper still keys some chat conversation memory by company+phone — multi-user browser sharing on one machine can collide locally |
| “HR Admin” as distinct role | Alias collapses to `owner` |
| Per-recruiter private candidate books | Not default; optional filters only |

---

## Data classification summary

### Shared company-wide (among entitled users)

- Jobs / positions
- Applications & candidates (default `all` scope)
- Interviews & assessments & reports metrics
- Overview queues / work-queue top-N
- Outbound delivery failure notifications
- Company settings, modules, intake mailboxes
- Org structure (branches/teams) and company audit activity
- Post-hire employee records (further narrowed for Team Managers by manager scope)

### Permission-scoped

- Who can invite/disable users (`users.manage`)
- Who can publish jobs / decide candidates / approve offers / export payroll / publish assessments
- Who can read Activity (`audit.read`)
- Who can manage assessments vs only view attempts/reports
- Team Manager employee reachability (`manager_scopes`)
- Grant-only scopes (`employees.*`, `assessment.publish`, `offer.hire_override`)

### Personal

- Dashboard login sessions
- Assistant chat history (per actor)
- Local browser storage (token, locale, last conversation id)
- Employee App self session (`/app/*`) — separate product surface
- External Google Calendar contents (today synced through shared `GOG_ACCOUNT`, not per-user OAuth)

---

## Role differences (practical)

| Capability | Owner | HR Manager | Recruiter | Hiring Manager | Team Manager | Viewer | Employee App |
|---|---|---|---|---|---|---|---|
| Invite/manage users | Yes | No (unless grant) | No | No | No | No | No |
| Company settings | Yes | Yes | No | No | No | No | No |
| Jobs publish/close | Yes | Yes | No | No | No | No | No |
| Jobs create/edit | Yes | Yes | Yes | No | No | No | No |
| Candidate manage/import | Yes | Yes | Yes | No | No | No | No |
| Candidate decide | Yes | Yes | No | No | No | No | No |
| Interviews | Yes | Yes | Yes | Yes | No | No | No |
| Assessments manage | Yes | Yes | Yes | No | No | No | No |
| Offer approve | Yes | Yes | No | Yes | No | No | No |
| Reports export | Yes | Yes | Yes | Yes | No | No | No |
| Audit activity | Yes | Yes | No | No | No | No | No |
| Post-hire manage | Full | Full | Limited/none | Manager subset | Scoped team | Read-ish | Self only |
| Payroll export | Yes | Yes | No | No | No | No | No |

---

## Is this safe for companies with many users?

**Yes, with operating rules:**

**Safe today**

- Separate logins and sessions per employee
- Strong tenant isolation
- Role permission matrix + module entitlements
- Team Manager fail-closed scoping for post-hire
- Audited sensitive mutations
- Selected optimistic concurrency on jobs + candidate ownership/lifecycle

**Needs operational awareness**

- Most recruiters see the **same** candidate/job pool
- Last-write-wins on many forms
- Notifications are shared operational queues, not personal assignment inboxes
- No Wathefni calendar ACL model yet
- “HR Admin” vs “Owner” naming can confuse least-privilege invites (both may land on `owner` via aliases)

**Not yet enterprise private-book safe** if a company expects recruiters to be fully isolated from each other’s candidates without using ownership filters and process discipline.

---

## Gaps before introducing Wathefni Calendar

1. **No first-party calendar entity model** (personal vs team vs company calendars, attendees, free/busy).
2. **No calendar ACL layer** beyond existing role permissions.
3. **All interview Google events currently land on one shared `GOG_ACCOUNT` primary calendar** — multi-user Calendar cannot reuse that as “each user’s calendar.”
4. **Assignment vs visibility** is incomplete: interviewer assignment exists, but lists/feedback remain company-wide for `interview.manage`.
5. **No realtime presence / booking lock** to prevent double-booking the same interviewer slot inside Wathefni (DB conflict checks are interview/panel-local only).
6. **Personal vs shared event semantics** must be designed explicitly; do not overload `candidate_interviews` as the company calendar.
7. **Notification fan-out** today is company operational / HR-phone broadcast, not “invitee-only” calendar alerts.
8. **Role taxonomy cleanup** recommended before calendar sharing rules: distinct Company Admin vs HR Admin vs Payroll Operator (`hr_admin` must stop aliasing to `owner`).
9. **Default candidate/job visibility policy** should be decided (company-shared vs owner-scoped default); stock UI never forces `mine`.
10. **Wave-2 custom roles** (`tenant_control_roles`) are not yet the live authority—calendar should not depend on them until cut over.
11. **Team directory privacy:** any active member can list peer emails/roles via `GET /dashboard/team` — calendar attendee pickers need an intentional privacy policy.
12. **OAuth ownership question:** who connects Calendar — company mailbox, each user, or both? Shared-settings last-write-wins will clash with multi-mailbox OAuth.

---

## Recommended calendar prerequisites (audit only — not implementing)

1. Define calendar object types: personal, team, company, interview-linked.
2. Bind visibility to attendee list + role + optional manager scope.
3. Add booking conflict checks against interviewer availability.
4. Keep Google sync as a channel, not the source of Wathefni truth.
5. Add per-user notification preferences for calendar invites.
6. Clarify whether Hiring Managers see all company interviews or only interviews they attend/own.

---

## Source map (primary)

| Concern | Primary authority |
|---|---|
| Roles/permissions | `wathefni-orchestrator/app.py` `ROLE_PERMISSIONS`, `dashboard_effective_permissions_for_user` |
| Auth context | `dashboard_context`, `dashboard_user_sessions`, `dashboard_users` |
| Team invites | `POST /dashboard/team/invites`, Settings Team UI |
| Manager scope | `manager_scopes`, `manager_scope_members`, `operator_manager_scope` |
| Candidate list scope | `prehire_applications_query` (`owner_scope`, `recruiter_owner`) |
| Jobs ownership field | `recruiter_user_id` on jobs APIs/UI |
| Notifications | `dashboard_prehire_notifications` |
| HR tasks | `dashboard_hr_tasks` + outbound delivery task helpers |
| Audit | `GET /dashboard/activity` + `record_admin_audit` |
| Employee self-service | `employee_app_context` `/app/*` |
| Future custom RBAC | `tenant_control_roles.py` (non-authoritative today) |

---

## Remaining unknowns

- Whether production still has any same-email multi-company `dashboard_users` rows in practice.
- Whether any production path still exercises legacy shared-token auth (code is harness-gated).
- Exact production Google Calendar / `GOG_ACCOUNT` binding per tenant and whether multiple Wathefni users already share one Google identity.
- Whether any tenant already relies on `owner_scope=mine` as default in a customized client (stock dashboard defaults to shared `all` and does not pass `owner_scope`).
- Whether Wave-2 `tc_*` role tables are seeded for WATHEFNI in production (code says additive/not authoritative).
- Whether `GET /dashboard/team` exposing peer permission lists is intentional product behavior.
- Operator mobile app session model relative to browser dashboard (separate backend; not fully expanded in this audit).

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Multiple employees can log into one company | **PASS** |
| Tenant isolation by `company_code` | **PASS** |
| Fixed role permission matrix exists | **PASS** |
| Team Manager post-hire scoping exists | **PASS** |
| Pre-hire default is company-shared among entitled users | **PASS (by design)** |
| Distinct Company Admin vs HR Admin vs HR Manager vs Payroll Operator vs Interviewer | **FAIL / gap** (aliases + missing roles) |
| Personal vs shared calendar product | **FAIL / not built** |
| General concurrent-edit protection across all pages | **PARTIAL** |
| Safe for many users with shared HR pool | **PASS with caveats** |
| Ready to introduce Wathefni Calendar without design work | **NO-GO until gaps above are closed** |

**Audit complete. No code changes made.**
